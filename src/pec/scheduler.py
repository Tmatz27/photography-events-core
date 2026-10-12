"""Collector scheduling, including read-only scheduling of durable owned polls."""
import asyncio
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from .logging import event


@dataclass(frozen=True)
class Policy:
    minimum_interval: float = 900
    timeout: float = 20
    maximum_backoff: float = 86400
    maximum_retry_after: float = 86400

    def __post_init__(self):
        values = (self.minimum_interval, self.timeout, self.maximum_backoff, self.maximum_retry_after)
        if (not all(math.isfinite(v) for v in values) or self.minimum_interval < 1
                or self.timeout <= 0 or self.maximum_backoff < self.minimum_interval
                or not 0 <= self.maximum_retry_after <= 86400 * 7
                or self.maximum_backoff > 86400 * 7):
            raise ValueError("Invalid collector policy")


@dataclass(frozen=True)
class State:
    next_allowed_at: datetime
    consecutive_failures: int = 0


class CollectionDeferred(Exception):
    """Internal ownership/due-time refusal; no provider request or HTTP status."""


def retry_seconds(value, now, maximum):
    """Clamp provider input before timedelta arithmetic; never infer a timezone."""
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                return 0
            seconds = max(0, (stamp.astimezone(UTC) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0
    if not math.isfinite(seconds) or seconds < 0:
        return 0
    if seconds > maximum:
        event("retry_after_clamped", code="provider_delay_exceeds_policy")
    return min(seconds, maximum)


def next_state(policy, previous, now, *, success, retry_after=None, jitter=random.random):
    failures = 0 if success else previous.consecutive_failures + 1
    delay = policy.minimum_interval if success else min(policy.maximum_backoff,
        policy.minimum_interval * 2 ** min(failures - 1, 20))
    if not success:
        delay = min(policy.maximum_backoff, delay + delay * 0.1 * jitter())
        delay = max(delay, retry_seconds(retry_after, now, policy.maximum_retry_after))
    return State(now + timedelta(seconds=delay), failures)


def failure_code(exc):
    if isinstance(exc, TimeoutError):
        return "timeout", None
    # aiohttp is an optional adapter dependency, not needed by Core runtime.
    try:
        from aiohttp import ClientError, ClientResponseError
    except ImportError:
        ClientError = ClientResponseError = ()
    if isinstance(exc, ClientResponseError):
        return f"http_{exc.status}", (exc.headers or {}).get("Retry-After")
    if isinstance(exc, OSError) or isinstance(exc, ClientError):
        return "network", None
    if isinstance(exc, ValueError):
        return "parser_failure", None
    return "adapter_failure", None


class Scheduler:
    """Legacy callbacks save local state; owned collectors persist their own outcomes."""
    def __init__(self):
        self.tasks = {}
        self.stop = asyncio.Event()

    async def wait(self, delay):
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=delay)
        except TimeoutError:
            pass

    def add(self, key, policy, collect, load, save=None, clock=lambda: datetime.now(UTC)):
        if key in self.tasks:
            raise ValueError("Source already scheduled")

        async def loop():
            try:
                state = await load(key)
            except Exception:
                event("scheduler_failure", source=key, code="state_load_failed")
                state = State(clock() + timedelta(seconds=policy.maximum_backoff), 1)

            async def reload():
                try:
                    current = await load(key)
                    # A disabled source, absent/past deadline or completion race
                    # must not create an immediate wake loop. This read-only
                    # floor never overwrites the persisted deadline/failure count.
                    deadline = current.next_allowed_at
                    if deadline <= clock():
                        deadline = clock() + timedelta(seconds=policy.minimum_interval)
                    return State(deadline, current.consecutive_failures)
                except Exception:
                    event("scheduler_failure", source=key, code="state_load_failed")
                    return State(clock() + timedelta(seconds=policy.maximum_backoff), state.consecutive_failures)

            while not self.stop.is_set():
                await self.wait(max(0, (state.next_allowed_at - clock()).total_seconds()))
                if self.stop.is_set():
                    break
                success, retry = False, None
                try:
                    async with asyncio.timeout(policy.timeout):
                        status, retry = await collect()
                    success = 200 <= status < 300
                    if not success:
                        event("source_collection_failure", source=key, code=f"http_{status}")
                except CollectionDeferred:
                    state = await reload()
                    continue
                except Exception as exc:
                    # CancelledError and other BaseExceptions propagate untouched.
                    code, retry = failure_code(exc)
                    event("parser_failure" if code == "parser_failure" else "source_collection_failure",
                          source=key, code=code)
                if save is None:
                    # The owned collector finalized under its lease. A stale
                    # scheduler must never save over another process/manual poll.
                    state = await reload()
                    continue
                state = next_state(policy, state, clock(), success=success, retry_after=retry)
                try:
                    await save(key, state)
                except Exception:
                    event("scheduler_failure", source=key, code="state_persist_failed")
        self.tasks[key] = asyncio.create_task(loop(), name=f"source:{key}")

    async def close(self):
        self.stop.set()
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

