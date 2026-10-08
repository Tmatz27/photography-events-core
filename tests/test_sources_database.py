"""M3A contract persistence/privacy and shadow calibration against real PostGIS."""

import copy
import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.ingestion import collect_fixture
from pec.patterns.api import read
from pec.sources import inaturalist, nws, wfigs
from pec.sources.calibration import POLICIES_SHADOW
from pec.sources.contracts import INATURALIST, NWS, WFIGS
from pec.sources.debug import calibration, contracts
from pec.sources.models import Batch
from pec.sources.storage import persist, collect, reserve
from pec.sources.http import FetchError
from test_patterns_database import data, db as database_fixture, sql, records
from test_patterns_database import pytestmark as database_marks
from test_database import NOW
from test_source_contracts import observation, perimeter, alert, forecast, client

db = database_fixture
pytestmark = database_marks


async def save(db, contract, values, hour=0, complete=True, snapshot=False):
    now = NOW + timedelta(hours=hour)
    parser = {"inaturalist": inaturalist.parse, "wfigs_current": wfigs.parse, "nws_live_context": nws.alert}[
        contract.source_key
    ]
    batch = Batch(
        complete=complete, snapshot=snapshot, provider_updated_at=now, requests=1, bytes_received=100
    )
    batch.parse(values, parser)
    await persist(db, contract, batch, now, now)
    return batch


async def normals(db):
    return await sql(
        db,
        """SELECT n.*,ST_AsGeoJSON(n.analysis_geometry) AS point,ST_AsGeoJSON(r.provider_geometry) AS raw_point,
        ST_AsGeoJSON(r.exact_geometry) AS raw_exact FROM normalized_observations n JOIN raw_observations r
        ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id WHERE s.key='inaturalist' ORDER BY n.id""",
    )


async def generate(db, hour=0):
    db.patterns_mode = "shadow"
    db.pattern_policies = POLICIES_SHADOW
    await collect_fixture(db, data(hour))
    await db.generate(data(hour))
    await db.wait_for_patterns()
    return await read(db, NOW + timedelta(hours=hour))


async def test_i1_i2_i3_i10_geometry_time_persistence(db):
    await save(
        db,
        INATURALIST,
        [
            observation(),
            observation(2, obscured=True),
            observation(3, geoprivacy="private", geojson=None),
            observation(4, time_observed_at=None),
        ],
    )
    rows = await normals(db)
    assert rows[0]["point"] and not rows[0]["raw_exact"]
    assert rows[1]["raw_point"] and not rows[1]["point"] and rows[1]["spatial_basis"] == "obscured_cell"
    assert not rows[2]["raw_point"] and not rows[2]["point"]
    assert rows[3]["observed_at"] is None and rows[3]["observed_date"] == NOW.date() and not rows[3]["point"]


async def test_i4_taxon_correction_supersedes(db):
    await save(db, INATURALIST, [observation(subject="bear")])
    await save(db, INATURALIST, [observation(updated_at=(NOW + timedelta(hours=1)).isoformat())], 1)
    rows = await normals(db)
    assert rows[0]["superseded_at"] and rows[1]["subject_key"] == "Danaus plexippus"


async def test_i5_corrected_evidence_time_not_fetch_renewal(db):
    r = observation()
    await save(db, INATURALIST, [r])
    corrected = {
        **r,
        "time_observed_at": (NOW - timedelta(days=10)).isoformat(),
        "updated_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    await save(db, INATURALIST, [corrected], 1)
    row = (await normals(db))[-1]
    assert row["observed_at"] == NOW - timedelta(days=10) and row["valid_until"] == NOW + timedelta(days=4)


async def test_i8_duplicate_uuid_one_current_no_renewal(db):
    await save(db, INATURALIST, [observation()])
    await save(db, INATURALIST, [observation()], 1)
    rows = await normals(db)
    assert len(rows) == 1 and rows[0]["valid_until"] == NOW + timedelta(days=14)
    diagnostics = await contracts(db, NOW + timedelta(hours=1))
    volume = diagnostics["items"][0]["utc_day_volume"]
    assert volume["unique_records"] == 1 and volume["duplicates"] == 1 and volume["accepted"] == 2


async def test_i6_privacy_change_redacts_historical_cluster_immediately(db):
    await save(db, INATURALIST, [observation(i, subject="bear") for i in range(1, 4)])
    initial = await generate(db)
    assert initial.clusters and not initial.clusters[0].redacted
    await save(
        db,
        INATURALIST,
        [observation(1, subject="bear", obscured=True, updated_at=(NOW + timedelta(hours=1)).isoformat())],
        1,
    )
    result = await read(db, NOW + timedelta(hours=1))
    assert result.clusters[0].redacted and result.clusters[0].metrics is None
    await generate(db, 1)
    rows = await normals(db)
    assert rows[0]["sensitive"] and rows[-1]["point"] is None


async def test_i7_bad_among_200_persisted_isolation(db):
    values = [observation(i) for i in range(1, 201)]
    values[40]["updated_at"] = "bad"
    await save(db, INATURALIST, values)
    assert len(await normals(db)) == 199
    r = (await sql(db, "SELECT * FROM source_runs"))[0]
    assert r["records_received"] == 200 and r["records_accepted"] == 199 and r["records_rejected"] == 1
    assert r["status"] == "parser_failure" and r["parser_error_counts"] == {"invalid_provider_update": 1}


async def test_malformed_known_correction_withdraws_old(db):
    await save(db, INATURALIST, [observation()])
    await save(db, INATURALIST, [observation(geoprivacy="future_enum")], 1)
    rows = await normals(db)
    assert rows[0]["superseded_at"] and rows[0]["sensitive"]


async def test_unreadable_uuid_known_numeric_id_protects_prior_fact(db):
    await save(db, INATURALIST, [observation()])
    await save(db, INATURALIST, [observation(uuid=None, geoprivacy="private", geojson=None)], 1)
    rows = await normals(db)
    assert len(rows) == 1 and rows[0]["superseded_at"] and rows[0]["sensitive"]


async def test_scope_correction_and_older_update_no_rollback(db):
    await save(db, INATURALIST, [observation()])
    r = observation(updated_at=(NOW + timedelta(hours=1)).isoformat())
    r["geojson"]["coordinates"] = [-80, 35]
    await save(db, INATURALIST, [r], 1)
    assert all(n["superseded_at"] for n in await normals(db))
    await save(db, INATURALIST, [observation()], 2)
    assert all(n["superseded_at"] for n in await normals(db))


async def test_b1_one_bear_signal_no_production(db):
    await save(db, INATURALIST, [observation(subject="bear")])
    result = await generate(db)
    value = await calibration(db, NOW)
    assert not result.clusters and value["items"][0]["level"] == "signal"
    assert not value["items"][0]["production_eligibility"]
    assert all(item.phenomenon_key == "tule_elk_rut" for item in (await db.opportunities(NOW)).items)


async def test_b2_b3_b4_multiple_presence_not_bear_count_or_behavior(db):
    await save(
        db,
        INATURALIST,
        [observation(i, subject="bear", description="feeding sow with cubs") for i in range(1, 4)],
    )
    result = await generate(db)
    assert result.clusters[0].metrics.independent_report_count == 3
    assert result.clusters[0].metrics.max_single_report_count is None
    assert result.clusters[0].metrics.behaviors == ["presence"]
    value = await calibration(db, NOW)
    assert value["items"][0]["level"] == "developing_watch" and value["items"][0]["animal_count"] is None
    assert all(p.state == "developing" for p in result.items)


async def test_b5_obscured_bear_not_density_or_destination(db):
    await save(db, INATURALIST, [observation(i, subject="bear", obscured=True) for i in range(1, 4)])
    result = await generate(db)
    assert not result.clusters and not result.preview_opportunities
    value = await calibration(db, NOW)
    assert value["items"][0]["level"] == "signal" and value["items"][0]["destination_key"] is None


async def test_i12_lower_confidence_never_density(db):
    await save(
        db, INATURALIST, [observation(i, subject="bear", quality_grade="needs_id") for i in range(1, 5)]
    )
    assert not (await generate(db)).clusters


async def test_m1_away_monarch_signal_hidden(db):
    r = observation()
    r["geojson"]["coordinates"] = [-120.5, 35.3]
    await save(db, INATURALIST, [r])
    value = await calibration(db, NOW)
    assert value["items"][1]["level"] == "signal" and not value["items"][1]["destination_key"]


async def test_m2_m6_near_grove_watch_without_authoritative_count(db):
    values = [observation(i) for i in range(1, 5)]
    for r in values:
        r["geojson"]["coordinates"] = [-120.6349, 35.1307]
    await save(db, INATURALIST, values)
    result = await generate(db)
    assert result.items[0].location.key == "pismo_grove"
    value = await calibration(db, NOW)
    assert value["items"][1]["level"] == "developing_watch"
    assert (
        not value["items"][1]["major_aggregation_confirmed"]
        and not value["items"][1]["production_eligibility"]
    )


@pytest.mark.parametrize(
    "change,intersects,expected",
    [
        ({}, True, "hold_candidate"),
        ({}, False, "no_intersection"),
        ({"attr_IncidentTypeCategory": "RX"}, True, "no_intersection"),
        ({"poly_FeatureCategory": "Wildfire Final Fire Perimeter"}, True, "no_intersection"),
    ],
)
async def test_w1_w2_w3_w4_m5_exact_destination_safety(db, change, intersects, expected):
    r = perimeter(**change)
    if not intersects:
        r["geometry"]["coordinates"] = [[[x + 0.1, y] for x, y in r["geometry"]["coordinates"][0]]]
    await save(db, WFIGS, [r], snapshot=True)
    value = await calibration(db, NOW)
    assert value["items"][1]["safety"] == expected
    assert value["items"][1]["level"] == "none"


async def test_w5_incident_geometry_correction_not_duplicate_fire(db):
    await save(db, WFIGS, [perimeter()], snapshot=True)
    r = perimeter(attr_ModifiedOnDateTime_dt=int((NOW + timedelta(hours=1)).timestamp() * 1000))
    r["geometry"]["coordinates"] = [[[x + 0.1, y] for x, y in r["geometry"]["coordinates"][0]]]
    await save(db, WFIGS, [r], 1, snapshot=True)
    current = await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")
    assert len(current) == 1
    assert (await calibration(db, NOW + timedelta(hours=1)))["items"][1]["safety"] == "no_intersection"


async def test_w6_database_polygon_failure_isolated(db):
    r = perimeter(2)
    r["geometry"]["coordinates"] = [
        [[-120.6, 35], [-120.5, 35.1], [-120.5, 35], [-120.6, 35.1], [-120.6, 35]]
    ]
    await save(db, WFIGS, [perimeter(), r, perimeter(3)], snapshot=True)
    assert len(await sql(db, "SELECT * FROM normalized_observations")) == 2
    run = (await sql(db, "SELECT * FROM source_runs"))[0]
    assert run["records_rejected"] == 1 and run["records_accepted"] == 2 and run["incomplete"]
    assert (await calibration(db, NOW))["items"][1]["safety"] == "unknown"


async def test_safety_snapshot_absence_only_after_complete(db):
    await save(db, WFIGS, [perimeter()], snapshot=True)
    await save(db, WFIGS, [], 1, complete=False, snapshot=True)
    assert len(await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")) == 1
    assert (await calibration(db, NOW + timedelta(hours=1)))["items"][1]["safety"] == "unknown"
    await save(db, WFIGS, [], 2, snapshot=True)
    assert not await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")


async def test_n3_alert_update_cancel_explicit_supersession(db):
    await save(db, NWS, [alert()])
    await save(db, NWS, [alert(2, messageType="Update", references=[{"identifier": "urn:test:1"}])], 1)
    assert len(await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")) == 1
    await save(db, NWS, [alert(3, messageType="Cancel", references=[{"identifier": "urn:test:2"}])], 2)
    assert not await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")


async def test_nws_model_reissue_same_values_retains_new_native_issue(db):
    first = Batch(received=1, records=[nws.forecast(forecast(50), NOW)], provider_updated_at=NOW)
    await persist(db, NWS, first, NOW, NOW)
    later = NOW + timedelta(minutes=10)
    second = Batch(received=1, records=[nws.forecast(forecast(50), later)], provider_updated_at=later)
    await persist(db, NWS, second, later, later)
    rows = await sql(db, "SELECT * FROM normalized_observations ORDER BY id")
    assert len(rows) == 2 and rows[0]["superseded_at"] and rows[1]["provider_updated_at"] == later
    assert rows[1]["observed_at"] == later and rows[1]["valid_until"] == rows[0]["valid_until"]


@pytest.mark.parametrize("temperature,word", [(50, "clustered"), (70, "flying")])
async def test_n5_m3_m4_temperature_does_not_create_aggregation(db, temperature, word):
    batch = Batch(received=1, records=[nws.forecast(forecast(temperature), NOW)], provider_updated_at=NOW)
    await persist(db, NWS, batch, NOW, NOW)
    value = await calibration(db, NOW)
    assert value["items"][1]["level"] == "none" and word in value["items"][1]["condition"]


async def test_live_provider_failure_does_not_degrade_m1(db):
    from test_database import DATA

    await collect_fixture(db, copy.deepcopy(DATA))
    await db.generate(DATA)
    before = (await db.opportunities(NOW)).model_dump()
    await save(db, INATURALIST, [], complete=False)
    after = (await db.opportunities(NOW)).model_dump()
    assert before == after and after["assessment_state"] == "complete"


async def test_l1_invalid_metadata_excluded_ledger_valid_publish(db):
    await collect_fixture(db, data(sightings=records(3)))
    async with db.engine.begin() as c:
        await c.execute(
            text(
                "UPDATE raw_observations SET raw_payload=raw_payload || CAST(:change AS jsonb) WHERE external_id='report-0'"
            ),
            {"change": json.dumps({"external_id": None})},
        )
        await c.execute(
            text(
                "UPDATE raw_observations SET raw_payload=raw_payload || CAST(:change AS jsonb) WHERE external_id='report-1'"
            ),
            {"change": json.dumps({"credible": "bad"})},
        )
    db.patterns_mode = "shadow"
    await db.generate(data())
    await db.wait_for_patterns()
    value = await read(db, NOW)
    assert value.analysis_state == "current" and value.identity_rejected_count == 1
    assert value.clusters[0].metrics.independent_report_count == 2


async def test_quota_persists_across_clients(db):
    from dataclasses import replace

    limited = replace(INATURALIST, requests_per_day=1)
    await reserve(db, limited)
    with pytest.raises(FetchError, match="daily_request_budget"):
        await reserve(db, limited)
    row = (await sql(db, "SELECT * FROM source_poll_state"))[0]
    assert row["requests_today"] == 1


async def test_optional_mocked_collect_and_cursor_commit(db):
    c, _ = client(INATURALIST, [dict(total_results=1, results=[observation()])])
    status, _ = await collect(db, INATURALIST, "PhotographyEventsCore-offline", client=c, clock=lambda: NOW)
    assert status == 200 and len(await normals(db)) == 1
    row = (await sql(db, "SELECT * FROM source_poll_state"))[0]
    assert row["cursor_updated_at"] == NOW


async def test_incident_pieces_union_and_transport_metrics(db):
    a, b = perimeter(), perimeter(2)
    b["properties"]["poly_IRWINID"] = a["properties"]["poly_IRWINID"]
    batch = Batch(provider_updated_at=NOW, snapshot=True)
    batch.parse([a, b], wfigs.parse)
    batch.records = wfigs.combine(batch.records, batch.rejected)
    await persist(db, WFIGS, batch, NOW, NOW)
    assert len(await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")) == 1
    run = (await sql(db, "SELECT * FROM source_runs"))[0]
    assert run["records_received"] == run["records_accepted"] == 2 and run["unique_records"] == 1


async def test_cancelled_collection_records_failure_without_m1(db):
    from pec.sources.http import Client
    from test_source_contracts import noop

    entered = asyncio.Event()

    async def blocked(url, ua):
        entered.set()
        await asyncio.Event().wait()

    c = Client(INATURALIST, "PhotographyEventsCore-offline", reserve=noop, transport=blocked)
    task = asyncio.create_task(
        collect(db, INATURALIST, "PhotographyEventsCore-offline", client=c, clock=lambda: NOW)
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    run = (await sql(db, "SELECT * FROM source_runs"))[0]
    assert run["status"] == "failure" and run["error_code"] == "collection_cancelled" and run["requests"] == 1
    assert not await sql(db, "SELECT * FROM assessment_runs")


async def test_authenticated_debug_does_not_expose_provider_points(db):
    await save(db, INATURALIST, [observation(geoprivacy="private", geojson=None)])
    body = json.dumps(await contracts(db, NOW), default=str)
    assert "00000000-0000" not in body and '"coordinates"' not in body and '"raw_payload"' not in body
