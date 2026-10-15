"""M3-only durable scheduler state; legacy M1 methods/pool remain unchanged."""

from datetime import timedelta

from sqlalchemy import text

from ..scheduler import State
from .contracts import CONTRACTS
from .storage import register


async def load(db, key, now, *, contract=None):
    contract = contract or CONTRACTS[key]

    async def operation(c):
        row = (
            (
                await c.execute(
                    text("""SELECT s.enabled,b.next_allowed_at,b.consecutive_failures,p.lease_until
            FROM sources s LEFT JOIN source_backoff b ON b.source_id=s.id
            LEFT JOIN source_poll_state p ON p.source_id=s.id WHERE s.key=:key"""),
                    dict(key=key),
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return State(now)
        deadline = max(row['next_allowed_at'] or now, row['lease_until'] or now)
        if not row['enabled']:
            deadline = max(deadline, now + timedelta(seconds=contract.polling_seconds))
        return State(deadline, row['consecutive_failures'] or 0)

    return await db.pattern_transaction(operation)


async def save(db, key, state):
    contract = CONTRACTS[key]

    async def operation(c):
        sid = await register(c, contract)
        await c.execute(
            text("""INSERT INTO source_backoff VALUES(:sid,:next,:failures)
            ON CONFLICT(source_id) DO UPDATE SET next_allowed_at=EXCLUDED.next_allowed_at,
            consecutive_failures=EXCLUDED.consecutive_failures"""),
            dict(sid=sid, next=state.next_allowed_at, failures=state.consecutive_failures),
        )

    await db.pattern_transaction(operation, write=True)
