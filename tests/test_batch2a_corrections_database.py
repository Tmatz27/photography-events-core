"""R1–R3 receipts, restart, revision and diagnostics in disposable real PostGIS."""

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from pec.config import Settings
from pec.database import Database, project_source
from pec.sources.contracts import CONTRACTS
from pec.sources.environment_contracts import history_contract, effective_contract
from pec.sources.storage import persist
from pec.sources.ownership import collect_owned
from pec.sources.diagnostics import read, IngestionResponse
from pec.sources.http import Response, NativeFloat
from pec.sources.models import Batch
from pec.sources import environment_models as m
from test_database import db as database_fixture, URL, pytestmark as database_marks
from test_patterns_database import sql
from test_batch2a_portable import NOW, fake, cdec_row
from test_batch2a_corrections_portable import nwps_batch, usgs_batch
from test_api import SETTINGS

db = database_fixture
pytestmark = database_marks


async def view(db, key, now=NOW):
    settings = replace(SETTINGS, patterns_mode="shadow", live_sources=True, source_keys=tuple(CONTRACTS))
    result = IngestionResponse(**await read(db, settings, now))
    assert len(result.items) == 81 and result.production_promotion is False
    return next(p for p in result.items if p.key == key)


async def test_R1_empty_history_receipts_and_checkpoint_survive_process_restart(db):
    contract = history_contract(CONTRACTS["cdec_snow"])
    db.collection_scope = {"history_start": "2026-10-12", "history_end": "2026-10-15"}
    client, _ = await fake("cdec_snow", [[]])
    status, _ = await collect_owned(
        db, contract, "PhotographyEventsCore-tests", client=client, clock=lambda: NOW
    )
    assert status == 200
    run = (await sql(db, "SELECT * FROM source_runs"))[0]
    outcome = run["context_payload"]["environment"]["stations"][0]
    assert run["status"] == "success" and run["records_accepted"] == run["records_received"] == 0
    assert outcome["outcome"] == "no_observations" and outcome["request_complete"]
    # New Database/client: no in-process checkpoint or lease state is reused.
    restarted = Database(Settings(URL, "test-only-" + "a" * 40))
    restarted.collection_scope = db.collection_scope
    try:
        for hour in (2, 4):
            client, calls = await fake("cdec_snow", [[] if hour == 2 else [cdec_row()]])
            status, _ = await collect_owned(
                restarted,
                contract,
                "PhotographyEventsCore-tests",
                client=client,
                clock=lambda: NOW + timedelta(hours=hour),
            )
            assert status == 200 and len(calls) == 1
        runs = await sql(restarted, "SELECT * FROM source_runs ORDER BY id")
        starts = [r["context_payload"]["environment"]["stations"][0]["window_start"] for r in runs]
        assert starts == [f"2026-10-{d}T00:00:00+00:00" for d in (12, 13, 14)]
        progress = (
            await sql(
                restarted,
                "SELECT checkpoint FROM source_poll_state p JOIN sources s ON s.id=p.source_id WHERE s.key='cdec_snow_history'",
            )
        )[0]["checkpoint"]
        assert progress["next_start"].startswith("2026-10-14T16:00:00")
        backoff = (await sql(restarted, "SELECT * FROM source_backoff"))[0]
        assert backoff["consecutive_failures"] == 0
        assert len(await sql(restarted, "SELECT * FROM environmental_assertions")) == 1
        diagnostic = await view(restarted, "cdec_snow", NOW + timedelta(hours=4))
        assert diagnostic.history_worker_health == "current"
        assert diagnostic.history_coverage.mode == "historical" and diagnostic.coverage is None
        assert diagnostic.history_coverage.measurement_freshness == "not_applicable"
    finally:
        await restarted.close()


async def test_R1_failed_history_window_retried_from_same_persisted_checkpoint(db):
    contract = history_contract(CONTRACTS["cdec_snow"])
    for hour, body in ((0, Response(503, {})), (2, [])):
        client, calls = await fake("cdec_snow", [body])
        status, _ = await collect_owned(
            db,
            contract,
            "PhotographyEventsCore-tests",
            client=client,
            clock=lambda: NOW + timedelta(hours=hour),
        )
        assert status == (503 if hour == 0 else 200)
        progress = (await sql(db, "SELECT checkpoint FROM source_poll_state"))[0]["checkpoint"]
        assert bool(progress) == bool(hour)
    runs = await sql(db, "SELECT * FROM source_runs ORDER BY id")
    assert [r["context_payload"]["environment"]["stations"][0]["window_start"] for r in runs] == [
        "2026-01-01T00:00:00+00:00"
    ] * 2


@pytest.mark.parametrize(
    "obs,forecast,absent,measurement,issued,state",
    [
        (5, 0, False, "stale", "current", "STALE"),
        (0, 5, False, "current", "stale", "STALE"),
        (0, 0, False, "current", "current", "UP"),
        (0, 0, True, "unknown", "current", "STALE"),
    ],
)
async def test_R2_persisted_native_clocks_and_source_health(
    db, obs, forecast, absent, measurement, issued, state
):
    batch, _ = await nwps_batch(obs, forecast, absent)
    await persist(db, CONTRACTS["nwps"], batch, NOW, NOW)
    diagnostic = await view(db, "nwps")
    assert diagnostic.coverage.measurement_freshness == measurement
    assert diagnostic.coverage.forecast_freshness == issued
    row = (await sql(db, "SELECT * FROM source_health_current WHERE key='nwps'"))[0]
    assert project_source(row, NOW).state == state
    values = await sql(db, "SELECT * FROM environmental_assertions WHERE evidence_kind='forecast'")
    assert len(values) == 2 and values[0]["issued_at"] == NOW - timedelta(days=forecast)
    assert values[0]["valid_at"] == NOW + timedelta(days=1)
    assert values[0]["numeric_value"] == Decimal("5.25")


async def test_R3_persisted_silent_coverage_then_independent_station_recovery(db):
    batch, _, _ = await usgs_batch(["current", "silent", "silent"])
    await persist(db, CONTRACTS["usgs_water"], batch, NOW, NOW)
    diagnostic = await view(db, "usgs_water")
    assert diagnostic.operational.status == "success"
    assert diagnostic.coverage.states["current"] == 1 and diagnostic.coverage.states["no_observations"] == 2
    row = (await sql(db, "SELECT * FROM source_health_current WHERE key='usgs_water'"))[0]
    assert project_source(row, NOW).state == "STALE"
    batch, _, _ = await usgs_batch(["current", "current", "current"])
    # Distinct provider series per station, as supplied in real USGS data.
    for f in batch.records:
        f.external_id = f.station_id + ":" + f.external_id
    await persist(db, CONTRACTS["usgs_water"], batch, NOW + timedelta(hours=1), NOW + timedelta(hours=1))
    diagnostic = await view(db, "usgs_water", NOW + timedelta(hours=1))
    assert diagnostic.coverage.states["current"] == 3
    assert diagnostic.coverage.measurement_freshness == "current"
    assert len(await sql(db, "SELECT * FROM environmental_assertions")) == 4


async def test_R3_partial_station_failure_keeps_siblings_and_blocks_checkpoint(db):
    batch, _, _ = await usgs_batch(["current", "failed", "current"])
    for f in batch.records:
        f.external_id = f.station_id + ":" + f.external_id
    await persist(db, CONTRACTS["usgs_water"], batch, NOW, NOW)
    diagnostic = await view(db, "usgs_water")
    assert diagnostic.coverage.states["current"] == 2 and diagnostic.coverage.states["failed"] == 1
    assert diagnostic.operational.records_accepted == 2 and diagnostic.state == "incomplete"
    assert (await sql(db, "SELECT checkpoint FROM source_poll_state"))[0]["checkpoint"] == {}
    assert len(await sql(db, "SELECT * FROM environmental_assertions")) == 2


async def test_native_json_precision_and_cdec_corrections_survive_storage(db):
    first = "1.2345678901234567890123456789"
    for hour, value in enumerate((first, "2.2345678901234567890123456789")):
        decoded = json.loads('{"value":' + value + "}", parse_float=NativeFloat)["value"]
        fact = m.cdec(cdec_row(value=decoded), "cdec_snow")
        await persist(
            db,
            CONTRACTS["cdec_snow"],
            Batch(records=[fact], received=1, requests=1),
            NOW + timedelta(hours=hour),
            NOW + timedelta(hours=hour),
        )
    rows = await sql(db, "SELECT * FROM environmental_assertions ORDER BY id")
    assert len(rows) == 2 and rows[0]["superseded_at"] and not rows[1]["superseded_at"]
    assert rows[0]["numeric_value"] == Decimal(first) and rows[0]["native_value"] == first
    assert rows[1]["numeric_value"] == Decimal(rows[1]["native_value"])
    assert (await sql(db, "SELECT version_num FROM alembic_version")) == [dict(version_num="0010")]


async def test_scope_quota_interval_is_persisted_in_owned_recovery_and_schedule(db):
    db.collection_scope = {"usgs_water": [f"USGS-{i:08}" for i in range(8)]}
    client, _ = await fake(
        "usgs_water", [dict(type="FeatureCollection", features=[], numberReturned=0, links=[])] * 16
    )
    contract = CONTRACTS["usgs_water"]
    status, _ = await collect_owned(
        db, contract, "PhotographyEventsCore-tests", client=client, clock=lambda: NOW
    )
    assert status == 200
    effective = effective_contract(contract, db.collection_scope)
    backoff = (await sql(db, "SELECT * FROM source_backoff"))[0]
    assert backoff["next_allowed_at"] >= NOW + timedelta(seconds=effective.polling_seconds)
    assert effective.polling_seconds > 3600 and backoff["consecutive_failures"] == 0
    diagnostic = await view(db, "usgs_water")
    # Diagnostic uses the same installed scope as the scheduler.
    settings = replace(SETTINGS, collection_scope=db.collection_scope)
    diagnostic = next(
        p for p in IngestionResponse(**await read(db, settings, NOW)).items if p.key == "usgs_water"
    )
    assert diagnostic.collection_interval_seconds == effective.polling_seconds


async def test_persistence_rejection_cannot_certify_station_current(db):
    batch, _, _ = await usgs_batch(["current"])
    batch.records[0].valid_at = NOW + timedelta(hours=3)
    await persist(db, CONTRACTS["usgs_water"], batch, NOW, NOW)
    diagnostic = await view(db, "usgs_water")
    assert diagnostic.coverage.states["incomplete"] == 1
    assert diagnostic.coverage.measurement_freshness == "unknown"
    assert diagnostic.operational.records_rejected == 1
    assert not await sql(db, "SELECT * FROM environmental_assertions")


async def test_ignored_older_poll_cannot_publish_current_station_coverage(db):
    newer, _, _ = await usgs_batch(["current"])
    newer.checkpoint = {"version": 2}
    await persist(db, CONTRACTS["usgs_water"], newer, NOW + timedelta(hours=2), NOW + timedelta(hours=2))
    older, _, _ = await usgs_batch(["current"])
    older.checkpoint = {"version": 1}
    await persist(db, CONTRACTS["usgs_water"], older, NOW + timedelta(hours=1), NOW + timedelta(hours=3))
    diagnostic = await view(db, "usgs_water", NOW + timedelta(hours=3))
    assert diagnostic.coverage.states["incomplete"] == 1
    assert diagnostic.coverage.measurement_freshness == "unknown"
    assert diagnostic.coverage.stations[0].error_code == "out_of_order_poll"
    assert (await sql(db, "SELECT checkpoint FROM source_poll_state"))[0]["checkpoint"] == {"version": 2}
    assert len(await sql(db, "SELECT * FROM environmental_assertions")) == 1
