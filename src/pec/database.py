"""Bounded async database access; SQL migrations are the authoritative models."""
import asyncio
import json
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from . import API_VERSION, CORE_VERSION, SCHEMA_VERSION
from .logging import event
from .schemas import Opportunity, OpportunityList, SourceHealth

VERSION = dict(core_version=CORE_VERSION, api_version=API_VERSION, schema_version=SCHEMA_VERSION)
# Versioned freshness policy, not executable JSON in the database.
SOURCE_TTL = {"nws_alerts": timedelta(hours=3), "fixture_observations": timedelta(hours=24)}
REQUIRED_SOURCES = frozenset(SOURCE_TTL)
MATERIAL = ("presentation", "eligibility", "significance", "confidence", "urgency", "evidence_state",
            "access_state", "safety_state", "condition_state", "reason", "definition_version",
            "definition_hash", "engine_version")


class DatabaseUnavailable(Exception):
    """Intentionally contains no database diagnostic string."""


class SchemaUnavailable(DatabaseUnavailable):
    pass


def project_source(row, now):
    stamp = row["provider_updated_at"] or row["last_success_at"]
    state = "DOWN" if row["status"] != "success" or not row["enabled"] else (
        "STALE" if stamp is None or now - stamp > SOURCE_TTL.get(row["key"], timedelta(hours=1)) else "UP")
    return SourceHealth(key=row["key"], state=state, last_attempt_at=row["last_attempt_at"],
                        last_success_at=row["last_success_at"], provider_updated_at=row["provider_updated_at"],
                        error_code=row["error_code"])


def envelope(assessment, items, sources, now, presentation=None, category=None):
    by_key = {s.key: s for s in sources}
    missing = sorted(key for key in REQUIRED_SOURCES if key not in by_key or by_key[key].state != "UP")
    degraded = sorted(s.key for s in sources if s.state != "UP")
    state = "complete"
    if not assessment or assessment["valid_until"] <= now or missing:
        state = "incomplete"
    elif assessment["state"] != "complete" or degraded:
        state = "degraded"
    public = []
    for item in items:
        if item.valid_until <= now or missing:
            # Stale saved intelligence is still readable as planning context,
            # but cannot remain a travel recommendation indefinitely.
            item = item.model_copy(update={"eligibility": False, "presentation": "held", "held": True,
                "watching": False, "safety_state": "unknown", "condition_state": "unknown",
                "reason": "Assessment stale or required source unavailable; refresh before acting.",
                "safety_summary": "Safety has not been checked with current data.",
                "blockers": sorted(set(item.blockers + ["current assessment unavailable"]))})
        if presentation is not None and item.presentation != presentation:
            continue
        if category is not None and item.category != category:
            continue
        public.append(item)
    return OpportunityList(**VERSION, generated_at=now,
        data_as_of=assessment["data_as_of"] if assessment else None, assessment_state=state,
        missing_required_sources=missing, degraded_sources=degraded, items=public)


class Database:
    def __init__(self, settings):
        self.timeout = settings.database_timeout
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5,
            max_overflow=0, pool_timeout=self.timeout, hide_parameters=True,
            connect_args={"timeout": self.timeout, "command_timeout": self.timeout,
                          "server_settings": {"statement_timeout": str(int(self.timeout * 1000))}})
        self.failed = False

    async def close(self):
        await self.engine.dispose()

    async def load_backoff(self, key, now):
        from .scheduler import State
        async def run():
            async with self.engine.connect() as c:
                row = (await c.execute(text("""SELECT b.next_allowed_at,b.consecutive_failures
                    FROM source_backoff b JOIN sources s ON s.id=b.source_id WHERE s.key=:key"""),
                    {"key": key})).mappings().first()
                return State(**row) if row else State(now)
        return await self._guard(run)

    async def save_backoff(self, key, state):
        async def run():
            async with self.engine.begin() as c:
                sid = (await c.execute(text("SELECT id FROM sources WHERE key=:key"), {"key": key})).scalar_one()
                await c.execute(text("""INSERT INTO source_backoff VALUES(:sid,:next,:failures)
                    ON CONFLICT(source_id) DO UPDATE SET next_allowed_at=EXCLUDED.next_allowed_at,
                    consecutive_failures=EXCLUDED.consecutive_failures"""),
                    {"sid": sid, "next": state.next_allowed_at, "failures": state.consecutive_failures})
        await self._guard(run)

    async def _guard(self, operation):
        try:
            async with asyncio.timeout(self.timeout):
                result = await operation()
        except SchemaUnavailable:
            event("schema_issue", code="schema_or_postgis_mismatch")
            raise
        except (SQLAlchemyError, OSError, TimeoutError):
            if not self.failed:
                event("database_unavailable", code="request_failed")
            self.failed = True
            raise DatabaseUnavailable() from None
        if self.failed:
            event("database_recovered")
            self.failed = False
        return result

    async def _check(self, connection):
        version = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        postgis = (await connection.execute(text("SELECT extversion FROM pg_extension WHERE extname='postgis'"))).scalar_one_or_none()
        if version != SCHEMA_VERSION or not postgis or not postgis.startswith("3.6"):
            raise SchemaUnavailable()
        # Check the actual application relations, not merely a responsive socket.
        await connection.execute(text("SELECT id FROM opportunities LIMIT 0"))
        await connection.execute(text("SELECT key FROM source_health_current LIMIT 0"))

    async def ready(self):
        async def run():
            async with self.engine.connect() as connection:
                await self._check(connection)
        await self._guard(run)

    async def health(self, now):
        async def run():
            async with self.engine.connect() as connection:
                await self._check(connection)
                rows = (await connection.execute(text("SELECT * FROM source_health_current ORDER BY key"))).mappings()
                return [project_source(row, now) for row in rows]
        return await self._guard(run)

    async def opportunities(self, now, presentation=None, category=None, occurrence_key=None):
        async def run():
            # A consistent read prevents a new assessment header being paired
            # with old opportunity membership during a concurrent evaluation.
            async with self.engine.connect() as base:
                connection = await base.execution_options(isolation_level="REPEATABLE READ")
                async with connection.begin():
                    await self._check(connection)
                    a = (await connection.execute(text("SELECT * FROM assessment_runs ORDER BY generated_at DESC,id DESC LIMIT 1"))).mappings().first()
                    rows = []
                    if occurrence_key:
                        rows = (await connection.execute(text("SELECT product FROM opportunities WHERE occurrence_key=:key"), {"key": occurrence_key})).scalars().all()
                    elif a:
                        rows = (await connection.execute(text("SELECT product FROM opportunities WHERE assessment_run_id=:id ORDER BY starts_at,occurrence_key"), {"id": a["id"]})).scalars().all()
                    health = (await connection.execute(text("SELECT * FROM source_health_current"))).mappings()
                    return envelope(a, [Opportunity.model_validate(row) for row in rows],
                                    [project_source(row, now) for row in health], now, presentation, category)
        return await self._guard(run)

    async def persist(self, data, items, normalized_ids=(), context_ids=()):
        """Transactional evaluated product write, shared by fixture and future collectors."""
        async def run():
            from datetime import datetime
            now = datetime.fromisoformat(data["now"])
            async with self.engine.begin() as c:
                # Single evaluator in M1. Lock survives neither crash nor commit.
                await c.execute(text("SELECT pg_advisory_xact_lock(7340191)"))
                aid = (await c.execute(text("""INSERT INTO assessment_runs(generated_at,data_as_of,valid_until,scope,state)
                    VALUES(:now,:now,:valid,'tule_elk_rut',:state) RETURNING id"""),
                    {"now": now, "valid": now + timedelta(hours=3), "state": "complete" if data.get("alerts") is not None else "incomplete"})).scalar_one()
                for item in items:
                    loc = item.location
                    lid = (await c.execute(text("""INSERT INTO locations(key,name,geometry,public_geometry,location_type,sensitivity)
                        VALUES(:key,:name,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
                        ST_SetSRID(ST_MakePoint(:lon,:lat),4326),'public_viewpoint','public')
                        ON CONFLICT(key) DO UPDATE SET name=EXCLUDED.name RETURNING id"""),
                        {"key": loc.key, "name": loc.name, "lat": loc.latitude, "lon": loc.longitude})).scalar_one()
                    await c.execute(text("INSERT INTO phenomenon_locations VALUES(:key,:location,'primary') ON CONFLICT DO NOTHING"), {"key": item.definition_key, "location": lid})
                    previous = (await c.execute(text("SELECT * FROM opportunities WHERE occurrence_key=:key"), {"key": item.occurrence_key})).mappings().first()
                    values = item.model_dump()
                    values.update(location_id=lid, assessment_run_id=aid, product=json.dumps(item.model_dump(mode="json")))
                    columns = ["occurrence_key", "phenomenon_key", "location_id", "assessment_run_id", "starts_at", "ends_at", "category",
                               *MATERIAL, "drive_minutes", "drive_basis", "awaiting", "definition_key", "data_as_of", "valid_until", "product"]
                    columns = list(dict.fromkeys(columns))
                    sql = f"INSERT INTO opportunities ({','.join(columns)}) VALUES ({','.join('CAST(:product AS jsonb)' if k == 'product' else ':' + k for k in columns)}) ON CONFLICT(occurrence_key) DO UPDATE SET "
                    sql += ','.join(f"{k}=EXCLUDED.{k}" for k in columns if k != "occurrence_key") + " RETURNING id"
                    oid = (await c.execute(text(sql), values)).scalar_one()
                    if previous is None or any(previous[k] != values[k] for k in MATERIAL):
                        await c.execute(text(f"INSERT INTO opportunity_revisions(opportunity_id,recorded_at,{','.join(MATERIAL)}) VALUES(:oid,:now,{','.join(':'+k for k in MATERIAL)})"), {**values, "oid": oid, "now": now})
                    for nid in normalized_ids:
                        await c.execute(text("INSERT INTO opportunity_observation_evidence VALUES(:oid,:nid,'SUPPORTING') ON CONFLICT DO NOTHING"), {"oid": oid, "nid": nid})
                    for rid in context_ids:
                        await c.execute(text("INSERT INTO opportunity_context_evidence VALUES(:oid,:rid,'NEUTRAL') ON CONFLICT DO NOTHING"), {"oid": oid, "rid": rid})
        await self._guard(run)

