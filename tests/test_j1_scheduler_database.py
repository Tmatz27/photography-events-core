"""J1 ownership refusals, persisted deadlines and stale scheduler/owner races."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.config import Settings
from pec.database import Database
from pec.scheduler import Scheduler, State, CollectionDeferred
from pec.sources import backoff
from pec.sources.contracts import INATURALIST
from pec.sources.http import Response, Client
from pec.sources.ownership import claim, collect_owned, finish
from test_api import SETTINGS
from test_database import NOW
from test_patterns_database import db as database_fixture, sql, pytestmark as database_marks
from test_source_contracts import client

db = database_fixture
pytestmark = database_marks
KEY = INATURALIST.source_key
UA = 'PhotographyEventsCore-J1-test'


def empty_client():
    return client(INATURALIST, [{'results': [], 'total_results': 0}])


async def wake(db, now, collect, *, initial=None, save=None):
    """Run one stale wake, then observe the next wait without waiting wall time."""
    scheduler = Scheduler()
    loads, waits = [], []

    async def load(key):
        loads.append(key)
        if len(loads) == 1:
            return initial or State(NOW, 9)
        return await backoff.load(db, key, now)

    async def wait(delay):
        waits.append(delay)
        if len(waits) == 2:
            scheduler.stop.set()

    scheduler.wait = wait
    scheduler.add(KEY, INATURALIST.scheduler_policy, collect, load, save, clock=lambda: now)
    await asyncio.wait_for(scheduler.tasks[KEY], 5)
    await scheduler.close()
    assert len(loads) == 2 and len(waits) == 2
    return waits


async def stored(db):
    return await sql(db, 'SELECT b.*,p.lease_token,p.lease_until FROM source_backoff b '
        'JOIN source_poll_state p ON p.source_id=b.source_id')


async def test_j1_manual_success_then_stale_scheduler_wake_preserves_zero_failures(db, caplog):
    transport, calls = empty_client()
    assert await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW) == (200, None)
    before = await stored(db)
    assert before[0]['consecutive_failures'] == 0
    assert before[0]['next_allowed_at'] == NOW + timedelta(seconds=1800)

    async def collect():
        return await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW + timedelta(seconds=1))

    waits = await wake(db, NOW + timedelta(seconds=1), collect)
    assert waits == [0, 1799] and len(calls) == 1
    assert await stored(db) == before and len(await sql(db, 'SELECT * FROM source_runs')) == 1
    assert 'source_collection_deferred' in caplog.text
    assert 'source_collection_failure' not in caplog.text and 'http_503' not in caplog.text


@pytest.mark.parametrize('reason', ['active_lease', 'not_due', 'disabled'])
async def test_j1_refusals_do_not_request_save_fail_or_change_persisted_state(db, reason, caplog):
    lease = await claim(db, INATURALIST, NOW)
    if reason != 'active_lease':
        assert await finish(db, INATURALIST, lease, NOW, status=200)
    if reason == 'disabled':
        async with db.pattern_engine.begin() as c:
            await c.execute(text('UPDATE sources SET enabled=FALSE WHERE key=:key'), dict(key=KEY))
    before = await stored(db)
    transport, calls = empty_client()

    async def collect():
        return await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW)

    async def forbidden_save(*args):
        raise AssertionError('Deferral must not save stale scheduler state')

    waits = await wake(db, NOW, collect, save=forbidden_save)
    assert waits == [0, 1800] and not calls and await stored(db) == before
    assert not await sql(db, 'SELECT * FROM source_runs')
    assert 'source_collection_failure' not in caplog.text and 'state_persist_failed' not in caplog.text


async def test_j1_reload_waits_for_active_lease_even_if_backoff_deadline_is_earlier(db):
    lease = await claim(db, INATURALIST, NOW)
    async with db.pattern_engine.begin() as c:
        await c.execute(text('UPDATE source_backoff SET next_allowed_at=:now'), dict(now=NOW))
    before = await stored(db)
    transport, calls = empty_client()

    async def collect():
        return await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW)

    waits = await wake(db, NOW, collect)
    assert waits == [0, (lease.until - NOW).total_seconds()]
    assert not calls and await stored(db) == before


async def test_j1_restart_loads_recovery_deadline_before_any_provider_request(db):
    await claim(db, INATURALIST, NOW)
    before = await stored(db)
    restarted = Database(Settings(db.pattern_engine.url, SETTINGS.api_token))
    scheduler = Scheduler()
    waits = []
    try:
        async def load(key):
            return await backoff.load(restarted, key, NOW + timedelta(seconds=1))

        async def collect():
            raise AssertionError('Restart must wait for persisted recovery')

        async def wait(delay):
            waits.append(delay)
            scheduler.stop.set()

        scheduler.wait = wait
        scheduler.add(KEY, INATURALIST.scheduler_policy, collect, load, clock=lambda: NOW + timedelta(seconds=1))
        await asyncio.wait_for(scheduler.tasks[KEY], 5)
        assert waits == [1799] and await stored(db) == before
    finally:
        await scheduler.close()
        await restarted.close()


async def test_j1_expired_lease_still_defers_until_recovery_deadline(db):
    lease = await claim(db, INATURALIST, NOW)
    later = lease.until + timedelta(seconds=1)
    transport, calls = empty_client()
    before = await stored(db)
    with pytest.raises(CollectionDeferred):
        await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: later)
    assert not calls and await stored(db) == before
    assert (await backoff.load(db, KEY, later)).next_allowed_at == NOW + timedelta(seconds=1800)


async def test_j1_expired_lease_authorizes_recovery_at_persisted_deadline(db):
    await claim(db, INATURALIST, NOW)
    later = NOW + timedelta(seconds=1800)
    transport, calls = empty_client()
    assert await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: later) == (200, None)
    row = (await stored(db))[0]
    assert len(calls) == 1 and row['lease_token'] is None and row['consecutive_failures'] == 0
    assert row['next_allowed_at'] == later + timedelta(seconds=1800)


@pytest.mark.parametrize('status', [429, 503])
async def test_j1_genuine_http_failure_persists_once_with_retry_after(db, status, caplog):
    transport, calls = client(INATURALIST, [Response(status, {}, retry_after='3600')])

    async def collect():
        return await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW)

    waits = await wake(db, NOW, collect, initial=State(NOW, 0))
    row = (await stored(db))[0]
    assert waits == [0, 3600] and len(calls) == 1
    assert row['consecutive_failures'] == 1 and row['lease_token'] is None
    assert row['next_allowed_at'] == NOW + timedelta(hours=1)
    run = (await sql(db, 'SELECT * FROM source_runs'))[0]
    assert run['status'] == 'failure' and run['requests'] == 1
    assert 'source_collection_failure' in caplog.text and f'http_{status}' in caplog.text
    assert 'source_collection_deferred' not in caplog.text


@pytest.mark.parametrize('old_status', [200, 429])
async def test_j1_stale_owner_cannot_overwrite_newer_backoff_or_release_owner(db, old_status):
    old = await claim(db, INATURALIST, NOW)
    later = NOW + timedelta(seconds=1801)
    new = await claim(db, INATURALIST, later)
    before = await stored(db)
    assert not await finish(db, INATURALIST, old, later, status=old_status, retry_after='99999')
    assert await stored(db) == before and before[0]['lease_token'] == new.token
    assert await finish(db, INATURALIST, new, later, status=429, retry_after='7200')
    newest = await stored(db)
    assert newest[0]['consecutive_failures'] == 2
    assert not await finish(db, INATURALIST, old, later, status=old_status)
    assert await stored(db) == newest and newest[0]['next_allowed_at'] == later + timedelta(hours=2)


async def test_j1_stale_successful_scheduler_cannot_overwrite_later_manual_failure(db):
    transport, _ = empty_client()
    newer_time = NOW + timedelta(seconds=1800)

    async def collect():
        result = await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW)
        # Another authorized manual poll finishes before the stale scheduler reload.
        later_transport, _ = client(INATURALIST, [Response(429, {}, retry_after='7200')])
        assert await collect_owned(db, INATURALIST, UA, client=later_transport,
            clock=lambda: newer_time) == (429, '7200')
        return result

    waits = await wake(db, NOW, collect)
    row = (await stored(db))[0]
    assert waits == [0, 9000] and row['consecutive_failures'] == 1 and row['lease_token'] is None
    assert row['next_allowed_at'] == newer_time + timedelta(hours=2)
    runs = await sql(db, 'SELECT * FROM source_runs ORDER BY id')
    assert [r['status'] for r in runs] == ['success', 'failure']


async def test_j1_timeout_preserves_recovery_and_cancelled_attempt(db, caplog):
    scheduler = Scheduler()
    from dataclasses import replace
    policy = replace(INATURALIST.scheduler_policy, timeout=0.25)
    waits = []

    async def blocked(url, ua):
        await asyncio.Event().wait()

    transport = Client(INATURALIST, UA, transport=blocked)

    async def collect():
        return await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW)

    async def load(key):
        return await backoff.load(db, key, NOW)

    async def wait(delay):
        waits.append(delay)
        if len(waits) == 2:
            scheduler.stop.set()

    scheduler.wait = wait
    scheduler.add(KEY, policy, collect, load, clock=lambda: NOW)
    await asyncio.wait_for(scheduler.tasks[KEY], 5)
    await scheduler.close()
    assert waits[0] == 0 and 1800 <= waits[1] <= 1980
    row = (await stored(db))[0]
    assert row['consecutive_failures'] == 1 and row['lease_token'] is None
    assert (await sql(db, 'SELECT * FROM source_runs'))[0]['error_code'] == 'collection_cancelled'
    assert 'timeout' in caplog.text


async def test_j1_repeated_genuine_failures_use_authoritative_exponential_backoff(db):
    first, _ = client(INATURALIST, [Response(503, {})])
    assert await collect_owned(db, INATURALIST, UA, client=first, clock=lambda: NOW) == (503, None)
    one = (await stored(db))[0]
    assert one['consecutive_failures'] == 1
    assert 1800 <= (one['next_allowed_at'] - NOW).total_seconds() <= 1980
    later = one['next_allowed_at']
    second, _ = client(INATURALIST, [Response(503, {})])
    assert await collect_owned(db, INATURALIST, UA, client=second, clock=lambda: later) == (503, None)
    two = (await stored(db))[0]
    assert two['consecutive_failures'] == 2
    assert 3600 <= (two['next_allowed_at'] - later).total_seconds() <= 3960


async def test_j1_failed_finalization_keeps_recovery_deadline_without_provider_failure(db, monkeypatch, caplog):
    from pec.sources import ownership

    async def failed_finish(*args, **kwargs):
        raise OSError('private database detail')

    monkeypatch.setattr(ownership, 'finish', failed_finish)
    transport, calls = empty_client()

    async def collect():
        return await collect_owned(db, INATURALIST, UA, client=transport, clock=lambda: NOW)

    waits = await wake(db, NOW, collect)
    row = (await stored(db))[0]
    assert waits == [0, 1800] and len(calls) == 1 and row['consecutive_failures'] == 1
    assert row['lease_token'] is None
    assert 'state_persist_failed' in caplog.text and 'source_collection_failure' not in caplog.text
    assert 'private database detail' not in caplog.text
