"""R13-R15: failures advance live state even if persistence is unavailable."""
import asyncio
from datetime import timedelta

import aiohttp
import pytest

from pec.scheduler import Policy, Scheduler, State, failure_code, next_state
from test_scheduler import NOW


@pytest.mark.parametrize("retry", ["1e9", "1e12"])
def test_r14_absurd_retry_after_clamped(retry, caplog):
    state = next_state(Policy(), State(NOW), NOW, success=False, retry_after=retry)
    assert state.next_allowed_at == NOW + timedelta(days=1)
    assert "retry_after_clamped" in caplog.text


@pytest.mark.parametrize("retry", ["nan", "inf", "-5", "garbage",
    "Sun, 27 Sep 2026 01:00:00", "Sat, 26 Sep 2026 01:00:00 GMT"])
def test_r15_invalid_retry_after_uses_own_backoff(retry):
    state = next_state(Policy(), State(NOW, 2), NOW, success=False, retry_after=retry, jitter=lambda: 0)
    assert state.next_allowed_at == NOW + timedelta(seconds=3600)


@pytest.mark.parametrize("exc,code", [
    (KeyError("sensitive payload must not be logged"), "adapter_failure"),
    (TimeoutError(), "timeout"),
    (ValueError(), "parser_failure"),
    (OSError(), "network"),
    (aiohttp.ClientConnectionError(), "network"),
    (aiohttp.ClientResponseError(None, (), status=503, headers={"Retry-After": "120"}), "http_503"),
])
async def test_r13_all_collector_failures_back_off(exc, code, caplog):
    scheduler = Scheduler()
    now, saves, loads, waits = [NOW], [], [], []

    async def wait(delay):
        waits.append(delay)
        now[0] += timedelta(seconds=delay)

    async def load(key):
        loads.append(key)
        return State(NOW)

    async def collect():
        raise exc

    async def save(key, state):
        saves.append(state)
        if len(saves) == 4:
            scheduler.stop.set()
        # R13b: every save fails. Live state must continue increasing.
        raise OSError("storage unavailable")

    scheduler.wait = wait
    scheduler.add("fixture", Policy(minimum_interval=10), collect, load, save, clock=lambda: now[0])
    await asyncio.wait_for(scheduler.tasks["fixture"], 1)
    await scheduler.close()
    assert len(loads) == 1
    assert [s.consecutive_failures for s in saves] == [1, 2, 3, 4]
    assert waits[2] >= 20 and waits[3] >= 40
    assert code in caplog.text
    assert "state_persist_failed" in caplog.text
    assert "sensitive payload" not in caplog.text
    assert failure_code(exc)[0] == code


async def test_non_success_status_uses_backoff_and_retry_after():
    scheduler = Scheduler()
    saved = []
    async def load(key):
        return State(NOW)
    async def collect():
        return 429, "3600"
    async def save(key, state):
        saved.append(state)
        scheduler.stop.set()
    scheduler.add("limited", Policy(), collect, load, save, clock=lambda: NOW)
    await asyncio.wait_for(scheduler.tasks["limited"], 1)
    await scheduler.close()
    assert saved == [State(NOW + timedelta(hours=1), 1)]
