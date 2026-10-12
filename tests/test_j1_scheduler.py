"""J1 portable scheduler deferrals and backward-compatible provider outcomes."""
import asyncio
from datetime import timedelta

import pytest

from pec.scheduler import CollectionDeferred, Policy, Scheduler, State
from test_scheduler import NOW


@pytest.mark.parametrize('reload_mode', ['future', 'past', 'unavailable'])
async def test_j1_deferred_reload_is_read_only_and_never_retries_immediately(reload_mode, caplog):
    scheduler = Scheduler()
    loads, saves, waits, calls = [], [], [], []
    policy = Policy(minimum_interval=10, maximum_backoff=100)

    async def load(key):
        loads.append(key)
        if len(loads) == 1:
            return State(NOW, 4)
        if reload_mode == 'unavailable':
            raise OSError('private database diagnostic')
        return State(NOW + timedelta(seconds=60 if reload_mode == 'future' else 0), 7)

    async def collect():
        calls.append(True)
        raise CollectionDeferred()

    async def save(key, state):
        saves.append(state)

    async def wait(delay):
        waits.append(delay)
        if len(waits) == 2:
            scheduler.stop.set()

    scheduler.wait = wait
    scheduler.add('fixture', policy, collect, load, save, clock=lambda: NOW)
    await asyncio.wait_for(scheduler.tasks['fixture'], 1)
    await scheduler.close()
    assert len(loads) == 2 and len(calls) == 1 and not saves
    assert waits == [0, {'future': 60, 'past': 10, 'unavailable': 100}[reload_mode]]
    assert 'source_collection_failure' not in caplog.text and 'http_503' not in caplog.text
    assert 'private database diagnostic' not in caplog.text


async def test_j1_owned_http_failure_reloads_persisted_failure_and_retry_after(caplog):
    scheduler = Scheduler()
    loads, waits = [], []

    async def load(key):
        loads.append(key)
        return State(NOW) if len(loads) == 1 else State(NOW + timedelta(hours=1), 8)

    async def collect():
        return 429, '3600'

    async def wait(delay):
        waits.append(delay)
        if len(waits) == 2:
            scheduler.stop.set()

    scheduler.wait = wait
    scheduler.add('fixture', Policy(), collect, load, clock=lambda: NOW)
    await asyncio.wait_for(scheduler.tasks['fixture'], 1)
    await scheduler.close()
    assert len(loads) == 2 and waits == [0, 3600]
    assert 'source_collection_failure' in caplog.text and 'http_429' in caplog.text

