"""M3-only durable scheduler state; legacy M1 methods/pool remain unchanged."""

from sqlalchemy import text

from ..scheduler import State
from .contracts import CONTRACTS
from .storage import register


async def load(db, key, now):
    CONTRACTS[key]

    async def operation(c):
        row = (
            (
                await c.execute(
                    text("""SELECT b.next_allowed_at,b.consecutive_failures FROM source_backoff b
            JOIN sources s ON s.id=b.source_id WHERE s.key=:key"""),
                    dict(key=key),
                )
            )
            .mappings()
            .first()
        )
        return State(**row) if row else State(now)

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
