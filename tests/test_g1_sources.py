"""G1 outcome classification, order invariance and asymmetric live safety."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.sources import inaturalist, storage
from pec.sources.contracts import INATURALIST, NWS, WFIGS
from pec.sources.debug import contracts
from pec.sources.models import Batch
from test_patterns_database import db as database_fixture, sql, pytestmark as database_marks
from test_source_contracts import observation, perimeter, alert
from test_source_corrections import poll, current, safety
from test_database import NOW

db = database_fixture
pytestmark = database_marks


async def latest(db):
    return (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]


async def active_ids(db):
    return {
        r["external_id"]
        for r in await sql(
            db,
            """SELECT r.external_id FROM raw_observations r
        JOIN normalized_observations n ON n.raw_observation_id=r.id WHERE n.superseded_at IS NULL""",
        )
    }


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("message", ["Update", "Cancel"])
async def test_g1_nws_original_and_reference_order_repeat_absence(db, reverse, message, caplog):
    original = alert()
    reference = alert(
        2,
        messageType=message,
        sent=(NOW + timedelta(minutes=1)).isoformat(),
        references=[{"identifier": "urn:test:1"}],
    )
    values = [original, reference]
    if reverse:
        values.reverse()
    for minute in (1, 2):
        batch = await poll(db, NWS, values, minute, snapshot=True)
        run = await latest(db)
        assert run["status"] == "success" and not run["incomplete"] and batch.complete
        assert not batch.rejected and run["records_rejected"] == 0 and run["parser_error_counts"] == {}
        assert await active_ids(db) == ({"urn:test:2"} if message == "Update" else set())
        response = await contracts(db, NOW + timedelta(minutes=minute))
        assert response["items"][2]["freshness"] == "current"
    counts = (await latest(db))["context_payload"]["outcome_counts"]
    assert counts["skipped_replay"] == 1 and counts["duplicate"] == 1 and counts["rejected_invalid"] == 0
    assert not any('"event": "parser_failure"' in r.getMessage() for r in caplog.records)
    # Original-only replay neither resurrects it nor shields a genuinely absent update.
    batch = await poll(db, NWS, [original], 3, snapshot=True)
    assert not await active_ids(db) and batch.complete and not batch.rejected
    await poll(db, NWS, [], 4, snapshot=True)
    assert not await active_ids(db) and (await latest(db))["status"] == "success"


@pytest.mark.parametrize("individual_fence", [False, True])
async def test_g1_stale_seen_record_preserves_current_but_retires_absent_sibling(db, individual_fence):
    newer = perimeter(attr_ModifiedOnDateTime_dt=int((NOW + timedelta(minutes=1)).timestamp() * 1000))
    await poll(db, WFIGS, [newer, perimeter(2)], 1, snapshot=True)
    if individual_fence:
        async with db.engine.begin() as c:
            await c.execute(
                text("UPDATE raw_observations SET state_poll_started_at=:stamp WHERE external_id=:eid"),
                dict(stamp=NOW + timedelta(minutes=4), eid="irwin:00000000-0000-4000-9000-000000000001"),
            )
    batch = await poll(db, WFIGS, [perimeter()], 2, snapshot=True)
    run = await latest(db)
    assert run["status"] == "success" and batch.complete and not batch.rejected
    assert len(await current(db)) == 1 and (await current(db))[0]["provider_updated_at"] == NOW + timedelta(
        minutes=1
    )
    assert run["context_payload"]["seen_ids"] == []
    assert len(run["context_payload"]["snapshot_seen_ids"]) == 1
    assert run["context_payload"]["outcome_counts"]["skipped_stale_version"] == 1
    assert run["context_payload"]["outcome_counts"]["ignored_out_of_order_poll"] == 0


@pytest.mark.parametrize("values", [[], [perimeter()]])
async def test_g1_ignored_entire_poll_does_not_advance_or_clear_or_certify(db, values):
    await poll(db, WFIGS, [perimeter()], 2, snapshot=True)
    before = (await sql(db, "SELECT * FROM source_poll_state"))[0]
    batch = await poll(db, WFIGS, values, 1, snapshot=True, completed=NOW + timedelta(minutes=3))
    after = (await sql(db, "SELECT * FROM source_poll_state"))[0]
    assert before == after and len(await current(db)) == 1 and not batch.complete
    run = await latest(db)
    assert run["status"] == "failure" and run["parser_error_counts"] == {}
    assert run["context_payload"]["poll_outcome"] == "ignored_out_of_order_poll"
    assert (
        not run["context_payload"]["complete_snapshot"] and run["context_payload"]["snapshot_seen_ids"] == []
    )
    assert run["context_payload"]["outcome_counts"]["ignored_out_of_order_poll"] == 1
    assert await safety(db, 3) == "hold_candidate"


@pytest.mark.parametrize("invalid", ["future", "geometry"])
@pytest.mark.parametrize("intersects", [False, True])
async def test_g1_incomplete_fire_positive_does_not_make_source_current(db, invalid, intersects):
    good, bad = perimeter(), perimeter(2)
    if not intersects:
        good["geometry"]["coordinates"] = [[[x + 0.1, y] for x, y in good["geometry"]["coordinates"][0]]]
    if invalid == "future":
        bad["properties"]["attr_ModifiedOnDateTime_dt"] = 4070908800000
    else:
        bad["geometry"]["coordinates"] = [
            [[-120.6, 35], [-120.5, 35.1], [-120.5, 35], [-120.6, 35.1], [-120.6, 35]]
        ]
    batch = await poll(db, WFIGS, [good, bad], snapshot=True)
    run = await latest(db)
    assert not batch.complete and run["status"] == "parser_failure" and run["incomplete"]
    assert run["records_accepted"] == 1 and run["records_rejected"] == 1
    counts = run["context_payload"]["outcome_counts"]
    assert counts["rejected_invalid"] == counts["incomplete_snapshot"] == 1
    assert not run["context_payload"]["complete_snapshot"]
    response = await contracts(db, NOW)
    assert response["items"][1]["freshness"] == "unknown"
    assert await safety(db) == ("hold_candidate" if intersects else "unknown")
    assert not await sql(db, "SELECT * FROM assessment_runs")


async def test_g1_only_invalid_future_fire_is_unknown(db):
    await poll(db, WFIGS, [perimeter(attr_ModifiedOnDateTime_dt=4070908800000)], snapshot=True)
    assert not await current(db) and await safety(db) == "unknown"


async def test_g1_complete_positive_negative_and_stale_fire(db):
    await poll(db, WFIGS, snapshot=True)
    assert await safety(db) == "no_intersection"
    await poll(db, WFIGS, [perimeter()], 1, snapshot=True)
    assert await safety(db, 1) == "hold_candidate" and await safety(db, 182) == "unknown"


@pytest.mark.parametrize("complete", [False, True])
async def test_g1_recent_receipt_cannot_renew_expired_native_fire(db, complete):
    old = int((NOW - timedelta(days=16)).timestamp() * 1000)
    await poll(
        db,
        WFIGS,
        [perimeter(attr_ModifiedOnDateTime_dt=old, poly_PolygonDateTime=old, poly_DateCurrent=old)],
        snapshot=True,
        complete=complete,
    )
    assert len(await current(db)) == 1 and (await current(db))[0]["valid_until"] < NOW
    # H1 supersedes native expiry for fresh qualifying WFIGS positive evidence.
    # The generic expiry remains unchanged; receipt age still expires the hold.
    assert await safety(db) == "hold_candidate"
    assert await safety(db, 181) == "unknown"


@pytest.mark.parametrize("complete", [False, True])
async def test_g1_fresh_current_view_retains_unexpired_native_fire_policy(db, complete):
    old = int((NOW - timedelta(days=2)).timestamp() * 1000)
    await poll(
        db,
        WFIGS,
        [perimeter(attr_ModifiedOnDateTime_dt=old, poly_PolygonDateTime=old, poly_DateCurrent=old)],
        snapshot=True,
        complete=complete,
    )
    assert (await current(db))[0]["valid_until"] == NOW + timedelta(days=13)
    assert await safety(db) == "hold_candidate"


@pytest.mark.parametrize(
    "properties",
    [
        dict(attr_IncidentTypeCategory="RX"),
        dict(poly_FeatureCategory="Wildfire Final Fire Perimeter"),
        dict(attr_ActiveFireCandidate=0),
    ],
)
async def test_g1_nonqualifying_fire_cannot_supply_incomplete_positive(db, properties):
    await poll(db, WFIGS, [perimeter(**properties)], snapshot=True, complete=False)
    assert await safety(db) == "unknown"


async def test_g1_diagnostics_expose_counts_without_provider_payloads_or_ids(db):
    await poll(
        db,
        NWS,
        [alert(), alert(2, messageType="Update", references=[{"identifier": "urn:test:1"}])],
        snapshot=True,
    )
    await poll(
        db,
        NWS,
        [alert(), alert(2, messageType="Update", references=[{"identifier": "urn:test:1"}])],
        1,
        snapshot=True,
    )
    response = await contracts(db, NOW + timedelta(minutes=1))
    operational = response["items"][2]["operational"]
    assert operational["skip_reason_counts"] == {"stale_reference_replay": 1}
    assert operational["outcome_counts"]["skipped_replay"] == 1 and operational["parser_error_counts"] == {}
    encoded = json.dumps(response, default=str)
    assert all(text not in encoded for text in ("urn:test:", "raw_payload", '"coordinates"', "00000000-0000"))


async def test_g1_collect_expected_replay_returns_success_not_retry_failure(db, monkeypatch):
    from pec.sources import nws

    async def fake_fetch(contract, client, now, **kwargs):
        batch = Batch(provider_updated_at=now, snapshot=True)
        batch.parse(
            [alert(), alert(2, messageType="Update", references=[{"identifier": "urn:test:1"}])], nws.alert
        )
        return batch

    monkeypatch.setattr(storage, "fetch", fake_fetch)
    for minute in (0, 1):
        status, _ = await storage.collect(
            db, NWS, "offline", client=object(), clock=lambda minute=minute: NOW + timedelta(minutes=minute)
        )
        assert status == 200 and (await latest(db))["status"] == "success"


async def test_g1_collect_invalid_fact_remains_retry_failure(db, monkeypatch):
    from pec.sources import wfigs

    async def fake_fetch(contract, client, now, **kwargs):
        batch = Batch(provider_updated_at=now, snapshot=True)
        batch.parse([perimeter(), perimeter(2, attr_ModifiedOnDateTime_dt=4070908800000)], wfigs.parse)
        return batch

    monkeypatch.setattr(storage, "fetch", fake_fetch)
    status, _ = await storage.collect(db, WFIGS, "offline", client=object(), clock=lambda: NOW)
    assert status == 502 and (await latest(db))["status"] == "parser_failure"
    assert await safety(db) == "hold_candidate"


async def test_g2_retired_id_not_refreshed_but_incremental_return_can_reinstate(db, monkeypatch):
    record = observation()
    await poll(db, INATURALIST, [record])
    await poll(db, INATURALIST, minute=1, unavailable=[record["uuid"]])
    selected = []

    async def fake_fetch(contract, client, now, *, cursor, known):
        selected.append(known)
        return (
            Batch(provider_updated_at=now)
            if len(selected) == 1
            else Batch(provider_updated_at=now, received=1, records=[inaturalist.parse(record)])
        )

    monkeypatch.setattr(storage, "fetch", fake_fetch)
    for minute in (2, 3):
        status, _ = await storage.collect(
            db,
            INATURALIST,
            "offline",
            client=object(),
            clock=lambda minute=minute: NOW + timedelta(minutes=minute),
        )
        assert status == 200
        assert len(await current(db)) == (0 if minute == 2 else 1)
    assert selected == [{}, {}] and (await current(db))[0]["sensitive"]
    assert (await current(db))[0]["observed_at"] == NOW and (await latest(db))["reinstated"] == 1
