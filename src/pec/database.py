"""Bounded DB units of work and consistent generation reads."""
import asyncio
from contextvars import ContextVar
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import event as sa_event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from . import API_VERSION, CORE_VERSION, SCHEMA_VERSION
from .logging import event
from .schemas import Opportunity, OpportunityList, SourceHealth

VERSION = dict(core_version=CORE_VERSION, api_version=API_VERSION, schema_version=SCHEMA_VERSION)
SOURCE_TTL = {"nws_alerts": timedelta(hours=3), "fixture_observations": timedelta(hours=24)}
REQUIRED_SOURCES = frozenset(SOURCE_TTL)
MATERIAL = ("presentation", "eligibility", "significance", "confidence", "urgency", "evidence_state",
            "access_state", "safety_state", "condition_state", "reason", "definition_version",
            "definition_hash", "engine_version")
DECISION = tuple(dict.fromkeys(("location_id", "starts_at", "ends_at", "category", *MATERIAL,
    "drive_minutes", "drive_basis", "awaiting", "definition_key", "data_as_of", "valid_until")))
_ACTIVE = ContextVar("core_database_operation", default=None)


class DatabaseUnavailable(Exception):
    """Machine code only. Never carry a driver/SQL/credential diagnostic."""
    code = "not_ready"


class SchemaUnavailable(DatabaseUnavailable):
    pass


class InvalidStoredProduct(DatabaseUnavailable):
    code = "invalid_stored_product"


class AssessmentConflict(DatabaseUnavailable):
    code = "assessment_conflict"


class GenerationFailed(DatabaseUnavailable):
    code = "generation_failed"


def project_source(row, now):
    stamp = row["provider_updated_at"] or row["last_success_at"]
    state = "DOWN" if row["status"] != "success" or not row["enabled"] else (
        "STALE" if stamp is None or now - stamp > SOURCE_TTL.get(row["key"], timedelta(hours=1)) else "UP")
    return SourceHealth(key=row["key"], state=state, last_attempt_at=row["last_attempt_at"],
                        last_success_at=row["last_success_at"], provider_updated_at=row["provider_updated_at"],
                        error_code=row["error_code"])


def envelope(assessment, items, sources, now, presentation=None, category=None, *, outdated=()):
    by_key = {s.key: s for s in sources}
    missing = sorted(key for key in REQUIRED_SOURCES if key not in by_key or by_key[key].state != "UP")
    degraded = sorted(set(outdated) | {s.key for s in sources if s.state != "UP"})
    state = "complete"
    if not assessment or assessment["valid_until"] <= now or missing:
        state = "incomplete"
    elif assessment["state"] != "complete" or degraded:
        state = "degraded"
    public = []
    for item in items:
        if item.valid_until <= now or state != "complete":
            item = item.model_copy(update={"eligibility": False, "presentation": "held", "held": True,
                "watching": False, "safety_state": "unknown", "condition_state": "unknown",
                "reason": "Assessment is not current; refresh before acting.",
                "awaiting": "A successful assessment using current required inputs.",
                "safety_summary": "Safety has not been checked with current data.",
                "safety_notes": [], "blockers": ["current assessment unavailable"]})
        if presentation is not None and item.presentation != presentation:
            continue
        if category is not None and item.category != category:
            continue
        public.append(item)
    return OpportunityList(**VERSION, assessment_id=assessment.get("id") if assessment else None,
        generated_at=now, data_as_of=assessment["data_as_of"] if assessment else None, assessment_state=state,
        missing_required_sources=missing, degraded_sources=degraded, items=public)


class Database:
    def __init__(self, settings):
        from .patterns.policy import POLICIES
        self.patterns_mode = settings.patterns_mode
        self.pattern_policies = POLICIES
        self.timeout = settings.database_timeout
        self.pattern_timeout = settings.pattern_timeout
        self._pattern_tasks = set()
        self.grace = timedelta(seconds=settings.evaluation_grace)
        # Perform readiness/ping SQL after checkout, where the deadline guard owns
        # the driver. An implicit pre-ping can hang before we can terminate it.
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=False, pool_size=5,
            max_overflow=0, pool_timeout=self.timeout, hide_parameters=True,
            connect_args={"timeout": self.timeout, "command_timeout": self.timeout * 2,
                          "server_settings": {"statement_timeout": str(int(self.timeout * 2000))}})
        self.failed = False
        # Shadow queries cannot consume the production pool or its deadline.
        self.pattern_engine = create_async_engine(settings.database_url, pool_pre_ping=False, pool_size=1,
            max_overflow=0, pool_timeout=self.pattern_timeout, hide_parameters=True,
            connect_args={"timeout": self.pattern_timeout, "command_timeout": self.pattern_timeout * 2,
                          "server_settings": {"statement_timeout": str(int(self.pattern_timeout * 2000))}})

        @sa_event.listens_for(self.engine.sync_engine, "checkout")
        def track_connection(connection, record, proxy):
            active = _ACTIVE.get()
            if active is not None:
                active.add(connection.driver_connection)

        @sa_event.listens_for(self.engine.sync_engine, "checkin")
        def untrack_connection(connection, record):
            active = _ACTIVE.get()
            if active is not None and connection is not None:
                active.discard(connection.driver_connection)
        sa_event.listen(self.pattern_engine.sync_engine, "checkout", track_connection)
        sa_event.listen(self.pattern_engine.sync_engine, "checkin", untrack_connection)

    async def close(self):
        tasks = tuple(self._pattern_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.pattern_engine.dispose()
        await self.engine.dispose()

    def start_patterns(self, aid, now):
        from .patterns.engine import run
        task = asyncio.create_task(run(self, aid, now, tuple(self.pattern_policies)))
        self._pattern_tasks.add(task)
        task.add_done_callback(self._pattern_tasks.discard)

    async def wait_for_patterns(self):
        """Explicit developer/test drain; production generation never awaits it."""
        while self._pattern_tasks:
            await asyncio.gather(*tuple(self._pattern_tasks))

    async def pattern_transaction(self, operation, *, write=False, timeout=None, repeatable=False):
        async def run():
            async with self.pattern_engine.connect() as base:
                connection = base if write and not repeatable else await base.execution_options(isolation_level="REPEATABLE READ")
                async with connection.begin():
                    try:
                        return await operation(connection)
                    except asyncio.CancelledError:
                        # A suspended Python operation may issue no driver SQL
                        # after terminate(), so explicitly discard its dead pool
                        # record before failure recording checks out a connection.
                        await connection.invalidate()
                        raise
        return await self._guard(run, timeout=timeout or self.pattern_timeout, isolated=True)

    async def _guard(self, operation, *, timeout=None, isolated=False):
        drivers = set()
        async def tracked():
            token = _ACTIVE.set(drivers)
            try:
                return await operation()
            finally:
                _ACTIVE.reset(token)
        task = asyncio.create_task(tracked())

        async def abort():
            # asyncpg terminate() aborts locally without waiting for the server.
            # Do this BEFORE cancellation enters SQLAlchemy's shielded graceful
            # close/rollback path, which can exceed the caller's deadline.
            for driver in drivers:
                driver.terminate()
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=0.5)
            if done:
                try:
                    task.result()
                except (Exception, asyncio.CancelledError):
                    pass
            else:
                # Consume a late exception; never expose its diagnostic.
                task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
                event("database_unavailable", code="cleanup_deadline")

        try:
            done, _ = await asyncio.wait({task}, timeout=timeout or self.timeout)
            if not done:
                await abort()
                raise TimeoutError()
            result = task.result()
        except asyncio.CancelledError:
            await abort()
            raise
        except SchemaUnavailable:
            event("schema_issue", code="schema_or_postgis_mismatch")
            raise
        except (SQLAlchemyError, OSError, TimeoutError):
            if isolated:
                raise DatabaseUnavailable() from None
            if not self.failed:
                event("database_unavailable", code="request_failed")
            self.failed = True
            raise DatabaseUnavailable() from None
        if self.failed and not isolated:
            event("database_recovered")
            self.failed = False
        return result

    async def transaction(self, operation, *, write=False):
        async def run():
            async with self.engine.connect() as base:
                connection = base if write else await base.execution_options(isolation_level="REPEATABLE READ")
                async with connection.begin():
                    return await operation(connection)
        return await self._guard(run)

    async def _check(self, connection):
        version = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        postgis = (await connection.execute(text("SELECT extversion FROM pg_extension WHERE extname='postgis'"))).scalar_one_or_none()
        if version != SCHEMA_VERSION or not postgis or not postgis.startswith("3.6"):
            raise SchemaUnavailable()
        await connection.execute(text("SELECT assessment_run_id FROM assessment_current LIMIT 0"))
        await connection.execute(text("SELECT opportunity_id FROM assessment_opportunities LIMIT 0"))
        await connection.execute(text("SELECT assessment_run_id FROM pattern_generation_runs LIMIT 0"))
        await connection.execute(text("SELECT key FROM source_health_current LIMIT 0"))

    async def ready(self):
        await self.transaction(self._check)

    async def health(self, now):
        async def run(c):
            await self._check(c)
            rows = (await c.execute(text("SELECT * FROM source_health_current ORDER BY key"))).mappings()
            return [project_source(row, now) for row in rows]
        return await self.transaction(run)

    async def opportunities(self, now, presentation=None, category=None, occurrence_key=None):
        async def run(c):
            await self._check(c)
            a = (await c.execute(text("""SELECT a.* FROM assessment_current p
                JOIN assessment_runs a ON a.id=p.assessment_run_id WHERE p.id=1"""))).mappings().first()
            if a is None:
                if (await c.execute(text("SELECT EXISTS(SELECT 1 FROM assessment_runs WHERE status='published')"))).scalar():
                    raise InvalidStoredProduct()
                return envelope(None, [], [], now)
            if a["status"] != "published":
                raise InvalidStoredProduct()
            conflict = (await c.execute(text("""SELECT EXISTS(SELECT 1 FROM assessment_runs
                WHERE data_as_of=:stamp AND error_code='input_conflict')"""), {"stamp": a["data_as_of"]})).scalar()
            if conflict:
                raise AssessmentConflict()
            rows = (await c.execute(text("""SELECT p.*,o.occurrence_key,o.phenomenon_key,
                p.product_sha256=encode(sha256(convert_to(p.product::text,'UTF8')),'hex') AS cache_intact
                FROM assessment_opportunities p JOIN opportunities o ON o.id=p.opportunity_id
                WHERE p.assessment_run_id=:aid ORDER BY p.starts_at,o.occurrence_key"""), {"aid": a["id"]})).mappings().all()
            if len(rows) != a["expected_items"]:
                raise InvalidStoredProduct()
            items = []
            try:
                for row in rows:
                    if not row["cache_intact"]:
                        raise InvalidStoredProduct()
                    product = Opportunity.model_validate(row["product"])
                    # The cache is versioned and validated against authoritative
                    # typed decisions. Corruption never becomes a partial success.
                    for key in (*DECISION, "occurrence_key", "phenomenon_key"):
                        if key != "location_id" and getattr(product, key) != row[key]:
                            raise InvalidStoredProduct()
                    if occurrence_key is None or row["occurrence_key"] == occurrence_key:
                        items.append(product.model_copy(update={"assessment_id": a["id"]}))
            except (ValidationError, TypeError, ValueError):
                raise InvalidStoredProduct() from None
            provenance = (await c.execute(text("""SELECT s.key,p.role,p.required,p.consulted,
                used.content_sha256 AS used_hash,used.status AS used_status,used.id AS used_id,
                latest.id AS latest_id,latest.completed_at AS latest_at,latest.content_sha256 AS latest_hash
                FROM assessment_sources p JOIN sources s ON s.id=p.source_id
                LEFT JOIN source_runs used ON used.id=p.source_run_id
                LEFT JOIN LATERAL (SELECT r.* FROM source_runs r WHERE r.source_id=s.id AND r.status='success'
                    ORDER BY r.completed_at DESC,r.id DESC LIMIT 1) latest ON TRUE
                WHERE p.assessment_run_id=:aid AND (p.required OR p.consulted)"""), {"aid": a["id"]})).mappings().all()
            keys = {p["key"] for p in provenance}
            health_rows = (await c.execute(text("SELECT * FROM source_health_current"))).mappings()
            health = [project_source(row, now) for row in health_rows if row["key"] in keys]
            outdated = {p["key"] for p in provenance if p["latest_id"] is not None
                and p["latest_id"] != p["used_id"] and now - p["latest_at"] >= self.grace
                and (p["used_status"] != "success" or p["latest_hash"] != p["used_hash"])}
            return envelope(dict(a), items, health, now, presentation, category, outdated=outdated)
        return await self.transaction(run)

    async def generate(self, data, *, evaluator=None):
        from .publication import generate
        return await generate(self, data, evaluator=evaluator)

    async def load_backoff(self, key, now):
        from .scheduler import State
        async def run(c):
            row = (await c.execute(text("""SELECT b.next_allowed_at,b.consecutive_failures
                FROM source_backoff b JOIN sources s ON s.id=b.source_id WHERE s.key=:key"""),
                {"key": key})).mappings().first()
            return State(**row) if row else State(now)
        return await self.transaction(run)

    async def save_backoff(self, key, state):
        async def run(c):
            sid = (await c.execute(text("SELECT id FROM sources WHERE key=:key"), {"key": key})).scalar_one()
            await c.execute(text("""INSERT INTO source_backoff VALUES(:sid,:next,:failures)
                ON CONFLICT(source_id) DO UPDATE SET next_allowed_at=EXCLUDED.next_allowed_at,
                consecutive_failures=EXCLUDED.consecutive_failures"""),
                {"sid": sid, "next": state.next_allowed_at, "failures": state.consecutive_failures})
        await self.transaction(run, write=True)

