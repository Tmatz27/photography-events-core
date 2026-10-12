"""Durable per-source ownership using only short isolated transactions."""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from ..logging import event
from .storage import register


@dataclass(frozen=True)
class Lease:
    token: uuid.UUID
    until: datetime


async def claim(db, contract, now):
    async def operation(c):
        await db._check(c)
        sid = await register(c, contract)
        state = (await c.execute(text("""SELECT s.enabled,p.* FROM source_poll_state p
            JOIN sources s ON s.id=p.source_id WHERE s.id=:sid FOR UPDATE OF p"""),
            dict(sid=sid))).mappings().one()
        due = (await c.execute(text("SELECT next_allowed_at FROM source_backoff WHERE source_id=:sid"),
            dict(sid=sid))).scalar_one_or_none()
        if not state['enabled'] or (state['lease_until'] and state['lease_until'] > now) or (due and due > now):
            return None
        lease = Lease(uuid.uuid4(), now + timedelta(seconds=contract.scheduler_policy.timeout + db.pattern_timeout + 30))
        await c.execute(text("UPDATE source_poll_state SET lease_token=:token,lease_until=:until WHERE source_id=:sid"),
            dict(sid=sid, token=lease.token, until=lease.until))
        # Persist a conservative next attempt BEFORE HTTP. A killed process cannot
        # erase the polling interval or cause immediate retry on every restart.
        recover = max(lease.until, now + timedelta(seconds=contract.polling_seconds))
        await c.execute(text("""INSERT INTO source_backoff VALUES(:sid,:next,1)
            ON CONFLICT(source_id) DO UPDATE SET next_allowed_at=GREATEST(source_backoff.next_allowed_at,EXCLUDED.next_allowed_at),
            consecutive_failures=source_backoff.consecutive_failures+1"""), dict(sid=sid, next=recover))
        return lease
    return await db.pattern_transaction(operation, write=True)


async def release(db, contract, lease):
    async def operation(c):
        await c.execute(text("""UPDATE source_poll_state SET lease_token=NULL,lease_until=NULL
            WHERE source_id=(SELECT id FROM sources WHERE key=:key) AND lease_token=:token"""),
            dict(key=contract.source_key, token=lease.token))
    await db.pattern_transaction(operation, write=True)


async def collect_owned(db, contract, user_agent, *, clock=lambda: datetime.now(UTC), client=None):
    from .storage import collect
    lease = await claim(db, contract, clock())
    if lease is None:
        event('source_collection_deferred', source=contract.source_key, code='disabled_leased_or_not_due')
        return 503, None
    try:
        return await collect(db, contract, user_agent, clock=clock, client=client, lease=lease)
    finally:
        try:
            await release(db, contract, lease)
        except Exception:
            # Expiry recovers ownership; never claim a successful cleanup.
            event('source_lease_failure', source=contract.source_key, code='release_failed')
