import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from pec.scheduler import Policy, Scheduler, State, next_state

NOW = datetime(2026, 9, 27, tzinfo=UTC)


@pytest.mark.parametrize("retry,seconds", [("3600", 3600), ("Sun, 27 Sep 2026 01:00:00 GMT", 3600), ("garbage", 900)])
def test_backoff_retry_after(retry, seconds):
    state = next_state(Policy(), State(NOW), NOW, success=False, retry_after=retry, jitter=lambda: 0)
    assert (state.next_allowed_at - NOW).total_seconds() == seconds
    assert state.consecutive_failures == 1


def test_backoff_is_bounded_and_success_resets():
    policy = Policy()
    state = next_state(policy, State(NOW, 99), NOW, success=False, jitter=lambda: 0)
    assert state.next_allowed_at == NOW + timedelta(seconds=86400)
    assert next_state(policy, state, NOW, success=True).consecutive_failures == 0


async def test_no_overlap_and_graceful_shutdown():
    scheduler = Scheduler()
    called, cancelled = asyncio.Event(), asyncio.Event()

    async def collect():
        called.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def load(key):
        return State(NOW)

    async def save(*args):
        raise AssertionError("cancelled job must not save success")

    scheduler.add("fixture", Policy(), collect, load, save, clock=lambda: NOW)
    with pytest.raises(ValueError):
        scheduler.add("fixture", Policy(), collect, load, save)
    await asyncio.wait_for(called.wait(), 1)
    await asyncio.wait_for(scheduler.close(), 1)
    assert cancelled.is_set() and not scheduler.tasks
