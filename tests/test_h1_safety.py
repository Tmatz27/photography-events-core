"""H1: native edit age never expires a verified fresh WFIGS Current hold."""

from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.sources import wfigs
from pec.sources.contracts import WFIGS
from pec.sources.debug import calibration, contracts
from pec.sources.models import Batch
from pec.sources.storage import persist
from test_database import NOW
from test_patterns_database import db as database_fixture, sql, pytestmark as database_marks
from test_source_contracts import perimeter
from test_source_corrections import current, safety

db = database_fixture
pytestmark = database_marks
OLD = NOW - timedelta(days=16)


def old_fire(index=1, *, native=OLD, **properties):
    epoch = int(native.timestamp() * 1000)
    return perimeter(
        index,
        attr_ModifiedOnDateTime_dt=epoch,
        poly_PolygonDateTime=epoch,
        poly_DateCurrent=epoch,
        **properties,
    )


async def receipt(db, values=(), minute=0, *, complete=True, completed=None, asof=OLD):
    stamp = NOW + timedelta(minutes=minute)
    batch = Batch(snapshot=True, complete=complete, provider_updated_at=asof)
    batch.parse(values, wfigs.parse)
    await persist(db, WFIGS, batch, stamp, completed or stamp)
    return batch


async def raw(db):
    return (await sql(db, "SELECT * FROM raw_observations ORDER BY id"))[0]


async def latest(db):
    return (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]


async def test_h1_1_old_edit_fresh_complete_current_feed_holds(db):
    await receipt(db, [old_fire()])
    n = (await current(db))[0]
    assert n["valid_until"] == OLD + timedelta(days=15) < NOW
    assert n["provider_updated_at"] == n["observed_at"] == OLD
    assert await safety(db) == "hold_candidate"
    assert (await latest(db))["status"] == "success"


async def test_h1_2_unchanged_hourly_receipts_over_sixteen_days_keep_hold(db):
    feature = old_fire()
    for hour in range(16 * 24 + 1):
        batch = await receipt(db, [feature], hour * 60)
        assert batch.complete and await safety(db, hour * 60) == "hold_candidate"
    rows = await sql(db, "SELECT * FROM normalized_observations")
    assert len(rows) == 1 and rows[0]["provider_updated_at"] == rows[0]["observed_at"] == OLD
    assert rows[0]["valid_until"] == OLD + timedelta(days=15)
    assert (await raw(db))["fetched_at"] == NOW + timedelta(days=16)
    counts = await sql(
        db, "SELECT sum(duplicates) AS duplicates,sum(reinstated) AS reinstated FROM source_runs"
    )
    assert counts[0]["duplicates"] == 384 and counts[0]["reinstated"] == 0


async def test_h1_3_receipt_window_boundary_and_expiry(db):
    await receipt(db, [old_fire()])
    boundary = WFIGS.freshness_seconds / 60
    assert await safety(db, boundary) == "hold_candidate"
    assert await safety(db, boundary + 1 / 60) == "unknown"


@pytest.mark.parametrize("invalid", ["future", "geometry"])
async def test_h1_4_old_edit_positive_survives_invalid_sibling(db, invalid):
    bad = old_fire(2)
    if invalid == "future":
        bad["properties"]["attr_ModifiedOnDateTime_dt"] = 4070908800000
    else:
        bad["geometry"]["coordinates"] = [
            [[-120.6, 35], [-120.5, 35.1], [-120.5, 35], [-120.6, 35.1], [-120.6, 35]]
        ]
    batch = await receipt(db, [old_fire(), bad])
    run = await latest(db)
    assert not batch.complete and run["status"] == "parser_failure" and run["incomplete"]
    assert run["records_accepted"] == run["records_rejected"] == 1
    assert await safety(db) == "hold_candidate"
    assert (await calibration(db, NOW))["sources"]["wfigs_current"] == "unknown"


@pytest.mark.parametrize("fresh_native", [False, True])
async def test_h1_5_complete_absence_retires_and_keeps_negative_proof_honest(db, fresh_native):
    await receipt(db, [old_fire()])
    await receipt(db, minute=1, asof=NOW + timedelta(minutes=1) if fresh_native else OLD)
    assert not await current(db) and (await raw(db))["retirement_reason"] == "snapshot_absent"
    assert await safety(db, 1) == ("no_intersection" if fresh_native else "unknown")


@pytest.mark.parametrize(
    "properties",
    [
        dict(attr_IncidentTypeCategory="RX"),
        dict(poly_FeatureCategory="Wildfire Final Fire Perimeter"),
        dict(attr_FireOutDateTime=int((NOW - timedelta(days=1)).timestamp() * 1000)),
        dict(poly_FeatureAccess="Internal"),
        dict(poly_FeatureAccess="Restricted"),
        dict(poly_FeatureStatus="Proposed"),
        dict(poly_FeatureStatus="Draft"),
        dict(attr_ActiveFireCandidate=0),
        dict(poly_IsVisible="No"),
        dict(poly_DeleteThis="Yes"),
    ],
)
async def test_h1_6_nonqualifying_old_perimeter_never_holds(db, properties):
    await receipt(db, [old_fire(**properties)])
    assert not (await current(db))[0]["source_metadata"]["qualifying_current_wildfire"]
    assert await safety(db) == "unknown"


async def test_h1_6_disabled_source_cannot_hold(db):
    await receipt(db, [old_fire()])
    async with db.engine.begin() as c:
        await c.execute(text("UPDATE sources SET enabled=FALSE WHERE key='wfigs_current'"))
    assert await safety(db) == "unknown"


@pytest.mark.parametrize("replay", ["older_poll", "stale_version"])
async def test_h1_7_replay_cannot_refresh_positive_receipt(db, replay):
    await receipt(db, [old_fire()])
    before = await raw(db)
    if replay == "older_poll":
        await receipt(db, minute=180, complete=False)
        batch = await receipt(db, [old_fire()], 120, completed=NOW + timedelta(minutes=241))
        assert batch.skipped[0][1] == "out_of_order_poll" and not batch.complete
    else:
        batch = await receipt(db, [old_fire(native=OLD - timedelta(days=1))], 241)
        assert batch.skipped[0][1] == "stale_provider_update" and batch.complete
    after = await raw(db)
    assert after["fetched_at"] == before["fetched_at"] == NOW
    assert after["state_poll_started_at"] == before["state_poll_started_at"] == NOW
    assert after["provider_updated_at"] == before["provider_updated_at"] == OLD
    assert await safety(db, 241) == "unknown"


async def test_h1_8_stale_native_debug_and_fresh_receipt_hold_are_distinct(db):
    await receipt(db, [old_fire()])
    view = (await contracts(db, NOW))["items"][1]
    assert view["freshness"] == "stale"
    assert view["operational"]["provider_updated_at"] == OLD
    assert view["operational"]["last_successful_fetch"] == NOW
    result = await calibration(db, NOW)
    assert result["sources"]["wfigs_current"] == "stale"
    assert result["items"][1]["safety"] == "hold_candidate"
    assert (await raw(db))["provider_updated_at"] == (await current(db))[0]["provider_updated_at"] == OLD


@pytest.mark.parametrize("case", ["empty", "away", "aged_receipt"])
async def test_h1_9_incomplete_without_fresh_intersection_never_clears(db, case):
    if case == "aged_receipt":
        await receipt(db, [old_fire()])
        await receipt(db, minute=241, complete=False)
        assert await safety(db, 241) == "unknown"
    else:
        values = []
        if case == "away":
            fire = old_fire()
            fire["geometry"]["coordinates"] = [[[x + 0.1, y] for x, y in fire["geometry"]["coordinates"][0]]]
            values = [fire]
        await receipt(db, values, complete=False)
        assert await safety(db) == "unknown"


async def test_h1_10_unchanged_old_incident_reinstates_with_original_native_time(db):
    fire = old_fire()
    await receipt(db, [fire])
    await receipt(db, minute=1)
    assert not await current(db)
    await receipt(db, [fire], 2)
    rows = await sql(db, "SELECT * FROM normalized_observations ORDER BY id")
    assert len(rows) == 2 and rows[0]["superseded_at"] and rows[1]["superseded_at"] is None
    assert all(n["observed_at"] == n["provider_updated_at"] == OLD for n in rows)
    assert all(n["valid_until"] == OLD + timedelta(days=15) for n in rows)
    assert (await latest(db))["reinstated"] == 1 and (await latest(db))["duplicates"] == 0
    assert await safety(db, 2) == "hold_candidate"
