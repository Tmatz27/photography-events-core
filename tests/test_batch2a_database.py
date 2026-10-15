"""Synthetic regression data in real PostGIS, distinct from genuine live receipts."""

import copy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from pec.sources.contracts import CONTRACTS
from pec.sources.environment_contracts import history_contract
from pec.sources import environment_models as m
from pec.sources.models import Batch
from pec.sources.storage import persist
from pec.sources.ownership import collect_owned
from pec.sources.http import Client, Response
from pec.scheduler import CollectionDeferred
from pec.retention import sweep
from test_patterns_database import db as database_fixture, sql, pytestmark as database_marks
from test_batch2a_portable import NOW, usgs_row, cdec_row, nwps_section

db = database_fixture
pytestmark = database_marks


async def save(db, key="usgs_water", fact=None, hour=0, complete=True, checkpoint=None):
    contract = CONTRACTS[key]
    if fact is None:
        fact = m.usgs(usgs_row())
    batch = Batch(records=[fact], received=1, requests=1, complete=complete, checkpoint=checkpoint)
    at = NOW + timedelta(hours=hour)
    await persist(db, contract, batch, at, at)
    return batch


async def rows(db):
    return await sql(db, "SELECT * FROM environmental_assertions ORDER BY id")


async def test_measurement_native_decimal_postgis_and_no_biological_assertion(db):
    await save(db)
    values = await rows(db)
    assert len(values) == 1 and values[0]["numeric_value"] == Decimal("1.234567890123456789")
    assert values[0]["unit"] == "ft^3/s" and values[0]["observed_at"] == NOW
    assert not await sql(db, "SELECT * FROM normalized_observations")
    geometry = await sql(
        db,
        "SELECT ST_SRID(provider_geometry) AS srid,ST_X(provider_geometry) AS lon FROM environmental_assertions",
    )
    assert geometry == [dict(srid=4326, lon=-119.6)]


async def test_identical_poll_is_idempotent_and_does_not_renew_measurement_time(db):
    await save(db)
    await save(db, hour=1)
    values = await rows(db)
    assert len(values) == 1 and values[0]["observed_at"] == values[0]["provider_updated_at"] == NOW
    assert values[0]["last_received_at"] == NOW + timedelta(hours=1)
    run = (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]
    assert run["duplicates"] == 1 and run["corrections"] == 0


async def test_provider_correction_keeps_old_value_and_native_quality(db):
    await save(db)
    value = usgs_row("2.125")
    value["properties"]["last_modified"] = (NOW + timedelta(hours=1)).isoformat()
    await save(db, fact=m.usgs(value), hour=1)
    values = await rows(db)
    assert len(values) == 2 and values[0]["superseded_at"] and not values[1]["superseded_at"]
    assert values[0]["numeric_value"] == Decimal("1.234567890123456789")
    assert values[1]["numeric_value"] == Decimal("2.125") and values[1]["quality"]["qualifier"] == "estimated"


async def test_cdec_missing_then_corrected_without_native_modified_time(db):
    await save(db, "cdec_snow", m.cdec(cdec_row(value=4), "cdec_snow"))
    await save(db, "cdec_snow", m.cdec(cdec_row(value=-9999), "cdec_snow"), hour=1)
    await save(db, "cdec_snow", m.cdec(cdec_row(value=5), "cdec_snow"), hour=2)
    values = await rows(db)
    assert len(values) == 3 and values[1]["withdrawn"] and values[1]["numeric_value"] is None
    assert values[1]["native_value"] == "-9999" and values[2]["numeric_value"] == 5
    assert all(v["provider_updated_at"] is None for v in values)
    assert values[2]["observed_at"].hour == 8


async def test_older_native_provider_version_cannot_replace_correction(db):
    row = usgs_row("9")
    row["properties"]["last_modified"] = (NOW + timedelta(hours=1)).isoformat()
    await save(db, fact=m.usgs(row), hour=1)
    batch = await save(db, hour=2)
    assert batch.skipped == [(m.usgs(usgs_row()).external_id, "stale_provider_update")]
    assert (await rows(db))[0]["numeric_value"] == 9


async def test_out_of_order_cdec_without_native_revision_time_is_fenced(db):
    await save(db, "cdec_snow", m.cdec(cdec_row(value=7), "cdec_snow"), hour=2)
    batch = await save(db, "cdec_snow", m.cdec(cdec_row(value=3), "cdec_snow"), hour=1)
    assert not batch.complete and (await rows(db))[0]["numeric_value"] == 7


async def test_history_and_incremental_share_one_raw_identity(db):
    await save(db)
    contract = history_contract(CONTRACTS["usgs_water"])
    batch = Batch(
        records=[m.usgs(usgs_row())],
        received=1,
        requests=1,
        checkpoint={"next_start": "2026-01-02T00:00:00Z"},
    )
    await persist(db, contract, batch, NOW + timedelta(hours=1), NOW + timedelta(hours=1))
    assert len(await sql(db, "SELECT * FROM raw_observations")) == len(await rows(db)) == 1
    runs = await sql(db, "SELECT * FROM source_runs ORDER BY id")
    assert runs[-1]["duplicates"] == 1
    states = await sql(
        db,
        "SELECT s.key,p.checkpoint FROM source_poll_state p JOIN sources s ON s.id=p.source_id ORDER BY s.key",
    )
    assert states[0]["checkpoint"] == {} and states[1]["checkpoint"]["next_start"] == "2026-01-02T00:00:00Z"


async def test_partial_parse_keeps_valid_siblings_but_not_checkpoint(db):
    contract = CONTRACTS["usgs_water"]
    batch = Batch(requests=1, checkpoint={"incremental_end": NOW.isoformat()})
    invalid = usgs_row("NaN")
    batch.parse([usgs_row(), invalid], m.usgs)
    await persist(db, contract, batch, NOW, NOW)
    assert len(await rows(db)) == 1 and not batch.complete
    assert (await sql(db, "SELECT checkpoint FROM source_poll_state"))[0]["checkpoint"] == {}
    run = (await sql(db, "SELECT * FROM source_runs"))[0]
    assert run["status"] == "parser_failure" and run["records_accepted"] == run["records_rejected"] == 1


async def test_forecast_issue_history_distinct_from_observed_and_new_cycle(db):
    section = nwps_section()
    row = dict(validTime=(NOW + timedelta(hours=3)).isoformat(), generatedTime=NOW.isoformat(), primary=2)
    await save(db, "nwps", m.nwps(row, section, "forecast", "POHC1", "primary", None))
    section2 = {**section, "issuedTime": (NOW + timedelta(hours=1)).isoformat()}
    await save(db, "nwps", m.nwps(row, section2, "forecast", "POHC1", "primary", None), hour=1)
    values = await rows(db)
    assert len(values) == 2 and all(
        v["evidence_kind"] == "forecast" and v["observed_at"] is None for v in values
    )
    assert len(await sql(db, "SELECT * FROM raw_observations")) == 2


async def test_future_actual_measurement_rejected_without_advancing_cursor(db):
    fact = m.usgs(usgs_row())
    fact.valid_at = NOW + timedelta(hours=2)
    batch = await save(db, fact=fact)
    assert not batch.complete and not await rows(db)
    assert batch.rejected[0][1] == "future_measurement_time"
    assert (await sql(db, "SELECT cursor_updated_at FROM source_poll_state"))[0]["cursor_updated_at"] is None


async def test_nps_unknown_native_time_is_not_retrieval_timestamp(db):
    fact = m.nps(dict(id="official-park", parkCode="yose", fullName="Yosemite"), "parks")
    await save(db, "nps", fact)
    await save(db, "nps", fact, hour=1)
    values = await rows(db)
    assert len(values) == 1 and values[0]["provider_updated_at"] is None and values[0]["observed_at"] is None
    assert values[0]["evidence_kind"] == "reference"


async def test_reference_correction_and_snapshot_membership_are_versioned(db):
    row = dict(
        id="official-park", parkCode="yose", fullName="Yosemite", operatingHours=[{"description": "old"}]
    )
    await save(db, "nps", m.nps(copy.deepcopy(row), "parks"))
    row["operatingHours"] = [{"description": "updated seasonal hours"}]
    await save(db, "nps", m.nps(row, "parks"), hour=1)
    values = await rows(db)
    assert len(values) == 2 and values[0]["raw_payload"]["operatingHours"][0]["description"] == "old"
    assert values[1]["metadata"]["current_access_proven"] is False


async def test_retention_prunes_raw_blobs_preserves_history_values_and_run_provenance(db):
    await save(db)
    await db.pattern_transaction(lambda c: sweep(c, NOW + timedelta(days=100)), write=True)
    values = await rows(db)
    assert len(values) == 1 and values[0]["raw_payload"] is None
    assert values[0]["numeric_value"] == Decimal("1.234567890123456789")
    assert len(await sql(db, "SELECT * FROM source_runs")) == 1


async def test_reference_knowledge_survives_bulk_payload_retention(db):
    fact = m.nps(
        dict(
            id="park",
            parkCode="yose",
            fullName="Yosemite",
            operatingHours=[{"description": "native seasonal hours"}],
            weatherInfo="official seasonal context",
        ),
        "parks",
    )
    await save(db, "nps", fact)
    await db.pattern_transaction(lambda c: sweep(c, NOW + timedelta(days=100)), write=True)
    value = (await rows(db))[0]
    assert value["raw_payload"] is None
    assert (
        value["metadata"]["reference_content"]["operatingHours"][0]["description"] == "native seasonal hours"
    )
    assert value["metadata"]["reference_content"]["weatherInfo"] == "official seasonal context"


async def test_environment_diagnostics_separate_native_freshness_and_credential_blocker(db):
    from pec.sources.diagnostics import read, IngestionResponse
    from test_api import SETTINGS

    await save(db)
    settings = replace(
        SETTINGS,
        patterns_mode="shadow",
        live_sources=True,
        source_keys=tuple(__import__("pec.sources.inventory", fromlist=["INVENTORY"]).INVENTORY),
    )
    response = IngestionResponse(**await read(db, settings, NOW))
    views = {p.key: p for p in response.items}
    assert (
        views["usgs_water"].adapter_implemented and views["usgs_water"].operational.historical_assertions == 1
    )
    assert views["nps"].state == "not_configured" and not views["cdec"].adapter_implemented
    assert len(views) == 81 and not response.production_promotion


async def test_owned_genuine_failure_and_j1_manual_deferral_unchanged(db):
    async def reserve():
        pass

    calls = []

    async def transport(url, agent):
        calls.append(url)
        return Response(429, {}, retry_after="600")

    contract = CONTRACTS["usgs_water"]
    client = Client(contract, "PhotographyEventsCore-tests", reserve=reserve, transport=transport)
    status, retry = await collect_owned(
        db, contract, "PhotographyEventsCore-tests", client=client, clock=lambda: NOW
    )
    assert status == 429 and retry == "600"
    with pytest.raises(CollectionDeferred):
        await collect_owned(db, contract, "PhotographyEventsCore-tests", client=client, clock=lambda: NOW)
    assert len(calls) == 1
    state = (await sql(db, "SELECT * FROM source_backoff"))[0]
    assert state["consecutive_failures"] == 1 and state["next_allowed_at"] >= NOW + timedelta(seconds=600)


async def test_live_and_history_own_independent_leases_and_recover_persisted_deadlines(db):
    from pec.sources.ownership import claim, finish
    from pec.sources.backoff import load

    live = CONTRACTS["usgs_water"]
    history = history_contract(live)
    leases = [await claim(db, c, NOW) for c in (live, history)]
    assert leases[0] and leases[1] and leases[0].token != leases[1].token
    recovered = await load(db, history.source_key, NOW + timedelta(seconds=1), contract=history)
    assert recovered.next_allowed_at >= NOW + timedelta(seconds=3600) and recovered.consecutive_failures == 1
    for contract, lease in zip((live, history), leases):
        batch = Batch(records=[m.usgs(usgs_row())], received=1, requests=1)
        await persist(db, contract, batch, NOW, NOW + timedelta(seconds=2), lease=lease)
        await finish(db, contract, lease, NOW + timedelta(seconds=3), status=200)
    assert len(await sql(db, "SELECT * FROM raw_observations")) == len(await rows(db)) == 1
    states = await sql(db, "SELECT * FROM source_backoff")
    assert len(states) == 2 and all(r["consecutive_failures"] == 0 for r in states)


async def test_cdec_freshness_uses_evidence_time_without_manufacturing_native_modification(db):
    from pec.sources.debug import freshness

    fact = m.cdec(cdec_row(value=4), "cdec_snow")
    batch = Batch(records=[fact], received=1, requests=1, native_evidence_asof=fact.valid_at)
    await persist(db, CONTRACTS["cdec_snow"], batch, NOW, NOW)
    row = (await sql(db, "SELECT s.enabled,r.* FROM source_runs r JOIN sources s ON s.id=r.source_id"))[0]
    assert row["provider_updated_at"] is None and row["native_evidence_asof"] == fact.valid_at
    assert freshness(CONTRACTS["cdec_snow"], row, NOW) == "current"
    assert freshness(CONTRACTS["cdec_snow"], row, NOW + timedelta(days=4)) == "stale"
