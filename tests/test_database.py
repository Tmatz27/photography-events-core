"""Real PostGIS integration tests; refuse a non-disposable database name."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from pec.config import Settings
from pec.database import Database
from pec.ingestion import ingest_fixture
from pec.retention import sweep
from pec.scheduler import State

URL = os.environ.get("CORE_TEST_DATABASE_URL")
pytestmark = [pytest.mark.database, pytest.mark.skipif(not URL, reason="Requires disposable PostGIS database")]
DATA = next(c["input"] for c in json.loads((Path(__file__).parent / "fixtures/legacy_tule_elk.json").read_text())['cases'] if c['name'] == 'elk_recent_presence')
NOW = datetime.fromisoformat(DATA["now"])


@pytest_asyncio.fixture
async def db():
    assert make_url(URL).database.endswith("_test"), "Never test against a production database"
    database = Database(Settings(URL, "test-only-" + "a" * 40))
    async with database.engine.begin() as c:
        await c.execute(text("TRUNCATE sources,locations,assessment_runs,observation_report_groups RESTART IDENTITY CASCADE"))
    yield database
    await database.close()


async def test_postgis_and_migration_revision(db):
    await db.ready()
    async with db.engine.connect() as c:
        assert (await c.execute(text("SELECT postgis_lib_version()"))).scalar().startswith("3.6")
        assert (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0003"
        assert (await c.execute(text("SELECT ST_SRID(ST_GeomFromText('POINT(-119.8 35.2)',4326))"))).scalar() == 4326


async def test_raw_to_normalized_to_product(db):
    items = await ingest_fixture(db, DATA)
    result = await db.opportunities(NOW)
    assert result.items[0] == items[0]
    assert result.assessment_state == "complete"
    async with db.engine.connect() as c:
        assert (await c.execute(text("SELECT count(*) FROM raw_observations"))).scalar() == 1
        assert (await c.execute(text("SELECT count(*) FROM opportunity_observation_evidence"))).scalar() == 1
        assert (await c.execute(text("SELECT count(*) FROM opportunity_context_evidence"))).scalar() == 2


async def test_external_identity_and_refetch_do_not_renew_evidence(db):
    await ingest_fixture(db, DATA)
    await ingest_fixture(db, {**DATA, "now": (NOW + timedelta(hours=1)).isoformat()})
    async with db.engine.connect() as c:
        rows = (await c.execute(text("SELECT * FROM raw_observations"))).mappings().all()
        assert len(rows) == 1 and rows[0]["observed_at"] == datetime.fromisoformat(DATA["sightings"][0]["observed_at"])
        assert (await c.execute(text("SELECT count(*) FROM normalized_observations"))).scalar() == 1
        assert (await c.execute(text("SELECT count(*) FROM source_runs"))).scalar() == 4


async def test_one_raw_can_produce_many_assertions(db):
    await ingest_fixture(db, DATA)
    async with db.engine.begin() as c:
        await c.execute(text("""INSERT INTO normalized_observations(raw_observation_id,subject_type,subject_key,
            observed_at,sensitive,precision_class,valid_until)
            SELECT raw_observation_id,'behavior','bugling',observed_at,FALSE,'withheld',valid_until
            FROM normalized_observations LIMIT 1"""))
        assert (await c.execute(text("SELECT count(*) FROM normalized_observations"))).scalar() == 2


@pytest.mark.parametrize("sql", [
    "INSERT INTO source_roles VALUES(1,'INVENTED')",
    "INSERT INTO source_roles VALUES(999,'SAFETY')",
    "UPDATE normalized_observations SET sensitive=TRUE,precision_class='exact'",
    "UPDATE assessment_opportunities SET confidence=101",
    "UPDATE assessment_opportunities SET eligibility=TRUE,presentation='planner'",
    "INSERT INTO raw_observations(source_id,external_id,fetched_at,parser_version) VALUES(1,'fixture-elk-1',now(),'test')",
])
async def test_database_constraints(db, sql):
    await ingest_fixture(db, DATA)
    with pytest.raises(IntegrityError):
        async with db.engine.begin() as c:
            await c.execute(text(sql))


async def test_route_baseline_uniqueness(db):
    await ingest_fixture(db, DATA)
    sql = """INSERT INTO route_baselines(origin_key,location_id,routing_profile,distance_miles,
        drive_minutes,provider,calculated_at) VALUES('fixture-home',1,'driving',90,100,'fixture',now())"""
    async with db.engine.begin() as c:
        await c.execute(text(sql))
    with pytest.raises(IntegrityError):
        async with db.engine.begin() as c:
            await c.execute(text(sql))


async def test_material_revisions_only(db):
    await ingest_fixture(db, DATA)
    await db.generate(DATA)
    async with db.engine.connect() as c:
        assert (await c.execute(text("SELECT count(*) FROM opportunity_revisions"))).scalar() == 1
    changed = {**DATA, "alerts": None, "now": (NOW + timedelta(hours=1)).isoformat()}
    await ingest_fixture(db, changed)
    async with db.engine.connect() as c:
        assert (await c.execute(text("SELECT count(*) FROM opportunity_revisions"))).scalar() == 2
        assert (await c.execute(text("SELECT count(*) FROM opportunities"))).scalar() == 1


async def test_failed_run_is_not_overwritten_by_success(db):
    await ingest_fixture(db, {**DATA, "alerts": None})
    await ingest_fixture(db, {**DATA, "now": (NOW + timedelta(hours=1)).isoformat()})
    async with db.engine.connect() as c:
        states = (await c.execute(text("SELECT status FROM source_runs r JOIN sources s ON s.id=r.source_id WHERE s.key='nws_alerts' ORDER BY r.id"))).scalars().all()
        assert states == ["failure", "success"]
    assert all(s.state == "UP" for s in await db.health(NOW))


async def test_sensitive_coordinates_do_not_leave_api(db):
    data = {**DATA, "sightings": [{**DATA["sightings"][0], "private_location": True}]}
    await ingest_fixture(db, data)
    result = (await db.opportunities(NOW)).model_dump_json()
    assert "exact_geometry" not in result
    assert '"latitude":35.2,' not in result
    async with db.engine.connect() as c:
        assert (await c.execute(text("SELECT analysis_geometry IS NOT NULL AND public_geometry IS NULL FROM normalized_observations"))).scalar()


async def test_retention_is_bounded_and_preserves_revisions(db):
    await ingest_fixture(db, DATA)
    async with db.engine.begin() as c:
        result = await sweep(c, NOW + timedelta(days=100), batch_size=1)
        assert result["payloads_redacted"] == 1
        assert (await c.execute(text("SELECT count(*) FROM opportunity_revisions"))).scalar() == 1
        assert (await c.execute(text("SELECT raw_payload IS NULL FROM raw_observations"))).scalar()


async def test_real_filter_empty_and_unknown_assessment(db):
    assert (await db.opportunities(NOW)).assessment_state == "incomplete"
    await ingest_fixture(db, DATA)
    assert (await db.opportunities(NOW, category="birds")).items == []
    assert (await db.opportunities(NOW, category="birds")).assessment_state == "complete"
    assert (await db.opportunities(NOW + timedelta(days=1))).assessment_state == "incomplete"


async def test_gist_index_and_metric_spatial_query(db):
    await ingest_fixture(db, DATA)
    async with db.engine.connect() as c:
        names = (await c.execute(text("SELECT indexname FROM pg_indexes WHERE tablename='normalized_observations'"))).scalars().all()
        assert "ix_normalized_analysis" in names
        assert (await c.execute(text("SELECT ST_DWithin(analysis_geometry::geography,ST_SetSRID(ST_MakePoint(-119.80,35.20),4326)::geography,100) FROM normalized_observations"))).scalar()


async def test_backoff_survives_new_database_client(db):
    await ingest_fixture(db, DATA)
    state = State(NOW + timedelta(hours=2), 3)
    await db.save_backoff("fixture_observations", state)
    restarted = Database(Settings(URL, "test-only-" + "a" * 40))
    try:
        assert await restarted.load_backoff("fixture_observations", NOW) == state
    finally:
        await restarted.close()
