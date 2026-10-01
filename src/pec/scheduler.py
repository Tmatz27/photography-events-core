"""One-process asyncio collector framework, no live collectors registered yet."""
import asyncio
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

    def __post_init__(self):
        if self.minimum_interval < 1 or self.timeout <= 0 or self.maximum_backoff < self.minimum_interval:
            raise ValueError("Invalid collector policy")


@dataclass(frozen=True)
class State:
    next_allowed_at: datetime
    consecutive_failures: int = 0


def next_state(policy, previous, now, *, success, retry_after=None, jitter=random.random):
    failures = 0 if success else previous.consecutive_failures + 1
    delay = policy.minimum_interval if success else min(policy.maximum_backoff,
        policy.minimum_interval * 2 ** min(failures - 1, 20))
    if not success:
        delay += delay * 0.1 * jitter()
    if retry_after:
        try:
            retry = float(retry_after)
        except (ValueError, TypeError):
            try:
                retry = (parsedate_to_datetime(retry_after).astimezone(UTC) - now).total_seconds()
            except (ValueError, TypeError, OverflowError):
                retry = 0
        if 0 <= retry < float("inf"):
            delay = max(delay, retry)
    return State(now + timedelta(seconds=delay), failures)


class Scheduler:
    """Callbacks load/save State in source_backoff and append attempts in source_runs.

    No unbounded tasks, duplicate jobs, hidden retries, or background exception
    leaks. Cancellation propagates so shutdown cannot trigger another request.
    """
    def __init__(self):
        self.tasks = {}
        self.stop = asyncio.Event()

    def add(self, key, policy, collect, load, save, clock=lambda: datetime.now(UTC)):
        if key in self.tasks:
            raise ValueError("Source already scheduled")

        async def loop():
            while not self.stop.is_set():
                try:
                    state = await load(key)
                    delay = max(0, (state.next_allowed_at - clock()).total_seconds())
                    try:
                        await asyncio.wait_for(self.stop.wait(), timeout=delay)
                        break
                    except TimeoutError:
                        pass
                    success, retry = False, None
                    try:
                        async with asyncio.timeout(policy.timeout):
                            status, retry = await collect()
                        success = 200 <= status < 300
                    except (TimeoutError, OSError):
                        event("source_collection_failure", source=key, code="network_failure")
                    except ValueError:
                        event("parser_failure", source=key, code="invalid_payload")
                    await save(key, next_state(policy, state, clock(), success=success, retry_after=retry))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    event("scheduler_failure", source=key, code="state_or_job_failure")
                    # A broken state store must not cause a tight retry loop.
                    try:
                        await asyncio.wait_for(self.stop.wait(), timeout=policy.minimum_interval)
                    except TimeoutError:
                        pass
        self.tasks[key] = asyncio.create_task(loop(), name=f"source:{key}")

    async def close(self):
        self.stop.set()
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

