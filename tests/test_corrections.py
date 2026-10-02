"""Required database regressions R1-R12, R16-R18, R21-R23 and N1/N3."""
import asyncio
import copy
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.api import create_app
from pec.database import AssessmentConflict, DatabaseUnavailable, GenerationFailed
from pec.ingestion import collect_fixture, ingest_fixture
from test_api import SETTINGS, get
from test_database import DATA, NOW, URL, db as database_fixture

db = database_fixture

pytestmark = [pytest.mark.database, pytest.mark.skipif(not URL, reason="Requires disposable PostGIS database")]
KEY = "tule_elk_rut-2026-09-15"


def data_at(hours=0, **changes):
    return {**copy.deepcopy(DATA), "now": (NOW + timedelta(hours=hours)).isoformat(), **changes}


async def query(db, sql, params=None):
    async with db.engine.connect() as c:
        return (await c.execute(text(sql), params or {})).mappings().all()


async def test_r1_stale_after_newer(db):
    await ingest_fixture(db, data_at(1))
    newer = await db.opportunities(NOW + timedelta(hours=1))
    result = await db.generate(data_at(0))
    assert result["status"] == "superseded"
    current = await db.opportunities(NOW + timedelta(hours=1))
    assert current.assessment_id == newer.assessment_id and len(current.items) == 1
    assert current.assessment_state == "complete"


async def test_r2_equal_replay_is_idempotent(db):
    await ingest_fixture(db, DATA)
    first = await db.opportunities(NOW)
    await ingest_fixture(db, DATA)
    second = await db.opportunities(NOW)
    assert first == second
    assert (await query(db, "SELECT count(*) AS n FROM opportunity_revisions"))[0]["n"] == 1


@pytest.mark.parametrize("first_limit,second_limit", [(6, 1), (1, 6)])
async def test_r23_equal_timestamp_different_inputs_fails_closed_in_both_orders(db, first_limit, second_limit):
    await ingest_fixture(db, data_at(max_drive_hours=first_limit))
    with pytest.raises(AssessmentConflict):
        await db.generate(data_at(max_drive_hours=second_limit))
    assert (await query(db, "SELECT count(*) AS n FROM assessment_runs WHERE error_code='input_conflict'"))[0]["n"] == 1
    app = create_app(SETTINGS, db, lambda: NOW)
    for path in ("/api/v1/opportunities", "/api/v1/opportunities/" + KEY):
        response = await get(app, path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "assessment_conflict"
    await ingest_fixture(db, data_at(1))
    assert (await db.opportunities(NOW + timedelta(hours=1))).assessment_state == "complete"


async def test_r3_concurrent_newer_older_twenty_iterations(db):
    await ingest_fixture(db, DATA)
    for index in range(20):
        older = (index * 2 + 1) / 60
        newer = older + 1 / 60
        attempts = [data_at(older), data_at(newer)]
        if index % 2:
            attempts.reverse()
        await asyncio.gather(*(db.generate(data) for data in attempts))
        current = await db.opportunities(NOW + timedelta(hours=newer))
        assert current.data_as_of == NOW + timedelta(hours=newer)
        assert current.assessment_state == "complete" and len(current.items) == 1


async def test_r4_generation_membership_list_and_detail(db):
    await ingest_fixture(db, data_at(1, horizon_days=366))
    await db.generate(data_at(0, horizon_days=60))
    app = create_app(SETTINGS, db, lambda: NOW + timedelta(hours=1))
    result = (await get(app, "/api/v1/opportunities")).json()
    assert len(result["items"]) == 2
    for item in result["items"]:
        detail = (await get(app, "/api/v1/opportunities/" + item["occurrence_key"])).json()
        assert detail == item and detail["assessment_id"] == result["assessment_id"]
    await ingest_fixture(db, data_at(2, horizon_days=60))
    response = await get(app, "/api/v1/opportunities/tule_elk_rut-2027-09-15")
    assert response.status_code == 404


async def test_r5_bad_record_isolated_and_future_admitted_without_refetch(db, caplog):
    valid = DATA["sightings"][0]
    future = {**valid, "external_id": "future", "observed_at": (NOW + timedelta(hours=2)).isoformat()}
    malformed = {**valid, "external_id": "bad", "observed_at": "not-a-timestamp"}
    await ingest_fixture(db, data_at(sightings=[valid, future, malformed]))
    counts = (await query(db, """SELECT r.records_accepted,r.records_rejected FROM source_runs r
        JOIN sources s ON s.id=r.source_id WHERE s.key='fixture_observations'"""))[0]
    assert counts == {"records_accepted": 2, "records_rejected": 1}
    links = await query(db, "SELECT * FROM opportunity_observation_evidence")
    assert len(links) == 1
    assert len(await query(db, "SELECT id FROM raw_observations")) == 3
    await db.generate(data_at(1.01))
    current = await db.opportunities(NOW + timedelta(hours=1.01))
    links = await query(db, "SELECT * FROM opportunity_observation_evidence WHERE assessment_run_id=:aid",
                        {"aid": current.assessment_id})
    assert len(links) == 2
    assert "not-a-timestamp" not in caplog.text


@pytest.mark.parametrize("age", [20, 1])
async def test_r6_provider_timestamp_correction_controls_freshness(db, age):
    first = {**DATA["sightings"][0], "observed_at": (NOW - timedelta(days=1 if age == 20 else 20)).isoformat()}
    await ingest_fixture(db, data_at(sightings=[first]))
    corrected = {**first, "observed_at": (NOW - timedelta(days=age)).isoformat()}
    await ingest_fixture(db, data_at(1, sightings=[corrected]))
    current = await db.opportunities(NOW + timedelta(hours=1))
    assert (current.items[0].evidence_state == "calendar_presence") == (age < 14)
    rows = await query(db, "SELECT observed_at,fetched_at FROM raw_observations")
    assert rows[0]["observed_at"] == NOW - timedelta(days=age)
    assert rows[0]["fetched_at"] == NOW + timedelta(hours=1)
    assertions = await query(db, "SELECT superseded_at FROM normalized_observations ORDER BY id")
    assert assertions[0]["superseded_at"] and assertions[1]["superseded_at"] is None


async def test_r7_coordinate_correction_moves_evidence_outside_radius(db):
    await ingest_fixture(db, DATA)
    changed = {**DATA["sightings"][0], "latitude": 40.123456789, "longitude": -123.987654321}
    await ingest_fixture(db, data_at(1, sightings=[changed]))
    assert (await db.opportunities(NOW + timedelta(hours=1))).items[0].evidence_state == "calendar"
    row = (await query(db, "SELECT ST_X(analysis_geometry) AS x, ST_Y(analysis_geometry) AS y FROM normalized_observations WHERE superseded_at IS NULL"))[0]
    assert row["x"] == changed["longitude"] and row["y"] == changed["latitude"]


async def test_r8_r9_sensitivity_is_monotonic_and_internal_evidence_retained(db, caplog):
    sighting = {**DATA["sightings"][0], "latitude": 35.212345678, "longitude": -119.812345678}
    for hour, private in enumerate([False, True, False]):
        await ingest_fixture(db, data_at(hour, sightings=[{**sighting, "private_location": private}]))
        current = await db.opportunities(NOW + timedelta(hours=hour))
        assert current.items[0].evidence_state == "calendar_presence"
        assert "35.212345678" not in current.model_dump_json()
        assert "-119.812345678" not in current.model_dump_json()
    rows = await query(db, "SELECT sensitive,public_geometry IS NULL AS hidden,analysis_geometry IS NOT NULL AS usable FROM normalized_observations")
    assert all(row["sensitive"] and row["hidden"] and row["usable"] for row in rows)
    assert "35.212345678" not in caplog.text


async def test_r10_species_correction_supersedes_old_assertion(db):
    await ingest_fixture(db, DATA)
    changed = {**DATA["sightings"][0], "scientific_name": "Cervus elaphus"}
    await ingest_fixture(db, data_at(1, sightings=[changed]))
    assert (await db.opportunities(NOW + timedelta(hours=1))).items[0].evidence_state == "calendar"
    rows = await query(db, "SELECT subject_key,superseded_at FROM normalized_observations ORDER BY id")
    assert len(rows) == 2 and rows[0]["superseded_at"] and rows[1]["superseded_at"] is None
    assert rows[1]["subject_key"] == changed["scientific_name"]


@pytest.mark.parametrize("changes", [{"count": 8}, {"behavior": "bugling"}, {"provider_note": "corrected metadata"}])
async def test_r10b_content_changes_renormalize_and_preserve_previous_evidence(db, changes):
    await ingest_fixture(db, DATA)
    original = (await query(db, "SELECT content_sha256 FROM raw_observations"))[0]["content_sha256"]
    await ingest_fixture(db, data_at(1, sightings=[{**DATA["sightings"][0], **changes}]))
    assert (await query(db, "SELECT content_sha256 FROM raw_observations"))[0]["content_sha256"] != original
    rows = await query(db, "SELECT * FROM normalized_observations ORDER BY id")
    assert len(rows) == 2 and rows[0]["superseded_at"] and rows[1]["superseded_at"] is None
    assert rows[1]["reported_count"] == changes.get("count", 1)
    assert rows[1]["behavior"] == changes.get("behavior")
    assert len(await query(db, "SELECT DISTINCT normalized_observation_id FROM opportunity_observation_evidence")) == 2


async def test_r11_no_cross_season_support(db):
    await ingest_fixture(db, data_at(horizon_days=366))
    rows = await query(db, """SELECT o.occurrence_key,count(e.normalized_observation_id) AS n
        FROM assessment_opportunities p JOIN opportunities o ON o.id=p.opportunity_id
        LEFT JOIN opportunity_observation_evidence e USING(assessment_run_id,opportunity_id)
        GROUP BY o.occurrence_key ORDER BY o.occurrence_key""")
    assert [row["n"] for row in rows] == [1, 0]


async def test_r12_generation_evidence_replaced_history_retained(db):
    await ingest_fixture(db, DATA)
    first = await db.opportunities(NOW)
    await ingest_fixture(db, data_at(24 * 20, sightings=[]))
    current = await db.opportunities(NOW + timedelta(days=20))
    assert not await query(db, "SELECT * FROM opportunity_observation_evidence WHERE assessment_run_id=:id", {"id": current.assessment_id})
    assert await query(db, "SELECT * FROM opportunity_observation_evidence WHERE assessment_run_id=:id", {"id": first.assessment_id})
    assert await query(db, "SELECT * FROM opportunity_revisions WHERE assessment_run_id=:id", {"id": first.assessment_id})


async def test_r16_partial_pipeline_failure_never_keeps_safe_complete(db):
    await ingest_fixture(db, DATA)
    first = await db.opportunities(NOW)
    warning = {"event": "High Wind Warning", "onset": NOW.isoformat(),
               "ends": (NOW + timedelta(days=1)).isoformat(), "same": ["006079"]}
    changed = data_at(1, alerts=[warning])
    await collect_fixture(db, changed)
    def broken(data):
        raise KeyError("private diagnostic")
    with pytest.raises(GenerationFailed):
        await db.generate(changed, evaluator=broken)
    now = NOW + timedelta(hours=1, seconds=31)
    assert all(s.state == "UP" for s in await db.health(now))
    current = await db.opportunities(now)
    assert current.assessment_id == first.assessment_id
    assert current.assessment_state == "degraded" and current.degraded_sources == ["nws_alerts"]
    assert current.items[0].held and not current.items[0].eligibility
    assert current.items[0].safety_state == "unknown"
    assert (await query(db, "SELECT count(*) AS n FROM assessment_runs WHERE status='failed'"))[0]["n"] == 1


async def test_r17_stable_id_source_rejects_idless_without_duplicates(db):
    record = {k: v for k, v in DATA["sightings"][0].items() if k != "external_id"}
    for hour in range(2):
        await ingest_fixture(db, data_at(hour, sightings=[record]))
    assert not await query(db, "SELECT id FROM raw_observations")
    assert not await query(db, "SELECT id FROM normalized_observations")
    assert not await query(db, "SELECT * FROM opportunity_observation_evidence")
    assert (await query(db, "SELECT sum(records_rejected) AS n FROM source_runs"))[0]["n"] == 2


async def test_n6_incremental_empty_batch_keeps_stored_current_presence(db):
    await ingest_fixture(db, DATA)
    await ingest_fixture(db, data_at(24, sightings=[]))
    current = await db.opportunities(NOW + timedelta(days=1))
    assert current.assessment_state == "complete"
    assert current.items[0].evidence_state == "calendar_presence"


async def test_r21_unrelated_newer_source_does_not_degrade(db):
    await ingest_fixture(db, DATA)
    async with db.engine.begin() as c:
        await c.execute(text("INSERT INTO sources(key,name,source_type) VALUES('unrelated','Unrelated test','fixture')"))
        await c.execute(text("""INSERT INTO source_runs(source_id,cycle_key,attempt_number,started_at,completed_at,status,provider_updated_at)
            SELECT id,'unrelated',1,:now,:now,'success',:now FROM sources WHERE key='unrelated'"""),
            {"now": NOW + timedelta(hours=1)})
    assert (await db.opportunities(NOW + timedelta(hours=1, seconds=31))).assessment_state == "complete"


async def test_r22_required_newer_inputs_observe_grace(db):
    await ingest_fixture(db, DATA)
    changed = {**DATA["sightings"][0], "count": 12}
    await collect_fixture(db, data_at(1, sightings=[changed]))
    assert (await db.opportunities(NOW + timedelta(hours=1))).assessment_state == "complete"
    current = await db.opportunities(NOW + timedelta(hours=1, seconds=31))
    assert current.assessment_state == "degraded"
    assert current.degraded_sources == ["fixture_observations"]


@pytest.mark.parametrize("damage", [
    "UPDATE assessment_opportunities SET product=product-'reason'",
    "UPDATE assessment_opportunities SET product=jsonb_set(product,'{confidence}','101')",
    "UPDATE assessment_opportunities SET product=jsonb_set(product,'{confidence}','12')",
    "UPDATE assessment_opportunities SET product=jsonb_set(product,'{location,latitude}','35.212345678')",
    "UPDATE assessment_runs SET expected_items=99 WHERE status='published'",
])
async def test_n3_corrupt_current_product_is_sanitized_503(db, damage):
    await ingest_fixture(db, DATA)
    async with db.engine.begin() as c:
        await c.execute(text(damage))
    app = create_app(SETTINGS, db, lambda: NOW)
    assert (await get(app, "/health/ready")).status_code == 200
    for path in ("/api/v1/opportunities", "/api/v1/opportunities/" + KEY):
        response = await get(app, path)
        assert response.status_code == 503 and response.json()["error"]["code"] == "invalid_stored_product"
        assert "SELECT" not in response.text and "postgresql" not in response.text


async def test_n1_writes_are_guarded_and_pool_recovers(db):
    db.timeout = 0.1
    async def slow(c):
        await c.execute(text("SELECT pg_sleep(10)"))
    start = asyncio.get_running_loop().time()
    with pytest.raises(DatabaseUnavailable):
        await db.transaction(slow, write=True)
    assert asyncio.get_running_loop().time() - start < 1.1
    assert db.engine.pool.checkedout() == 0
    db.timeout = 3
    await db.ready()


@pytest.mark.parametrize("changes", [
    {"scientific_name": ""}, {"latitude": None}, {"latitude": float("inf")},
    {"observed_at": "invalid"}, {"observed_at": "9999-12-31T23:00:00+00:00"}, {"count": -1},
])
async def test_r5_malformed_variants_never_discard_good_record(db, changes):
    record = DATA["sightings"][0]
    await ingest_fixture(db, data_at(sightings=[record, {**record, "external_id": "malformed", **changes}]))
    current = await db.opportunities(NOW)
    assert current.items[0].evidence_state == "calendar_presence"
    assert (await query(db, "SELECT sum(records_rejected) AS n FROM source_runs"))[0]["n"] == 1
    assert len(await query(db, "SELECT id FROM raw_observations")) == 2
