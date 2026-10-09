"""Independent review R1-R10/T1-T7: real lifecycle, ordering and privacy."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.sources import inaturalist, nws, wfigs, backoff
from pec.sources.contracts import INATURALIST, NWS, WFIGS
from pec.sources.debug import calibration
from pec.sources.models import Batch
from pec.sources.storage import persist
from pec.scheduler import State
from pec.database import Database
from pec.config import Settings
from test_database import NOW, URL
from test_patterns_database import db as database_fixture, sql
from test_patterns_database import pytestmark as database_marks
from test_source_contracts import observation, perimeter, alert, forecast
from test_sources_database import normals, generate
from pec.patterns.api import read

db = database_fixture
pytestmark = database_marks


async def poll(
    db, contract, values=(), minute=0, *, complete=True, snapshot=False, unavailable=(), completed=None
):
    started = NOW + timedelta(minutes=minute)
    batch = Batch(
        complete=complete, snapshot=snapshot, provider_updated_at=started, unavailable_ids=set(unavailable)
    )
    batch.parse(
        values,
        {"inaturalist": inaturalist.parse, "wfigs_current": wfigs.parse, "nws_live_context": nws.alert}[
            contract.source_key
        ],
    )
    await persist(db, contract, batch, started, completed or started)
    return batch


async def current(db):
    return await sql(db, "SELECT * FROM normalized_observations WHERE superseded_at IS NULL")


async def safety(db, minute=0):
    return (await calibration(db, NOW + timedelta(minutes=minute)))["items"][1]["safety"]


async def test_r1_identical_fire_reappears_hold_and_history(db):
    await poll(db, WFIGS, [perimeter()], snapshot=True)
    assert await safety(db) == "hold_candidate"
    first = (await sql(db, "SELECT content_sha256 FROM source_runs ORDER BY id"))[-1]["content_sha256"]
    await poll(db, WFIGS, minute=1, snapshot=True)
    assert await safety(db, 1) == "no_intersection" and not await current(db)
    retired = (await sql(db, "SELECT content_sha256 FROM source_runs ORDER BY id"))[-1]["content_sha256"]
    await poll(db, WFIGS, [perimeter()], 2, snapshot=True)
    assert await safety(db, 2) == "hold_candidate" and len(await current(db)) == 1
    history = await sql(db, "SELECT * FROM normalized_observations ORDER BY id")
    assert len(history) == 2 and history[0]["superseded_at"] and history[1]["observed_at"] == NOW
    restored = (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]
    assert first != retired and restored["content_sha256"] == first and restored["reinstated"] == 1


async def test_r2_identical_alert_reappears(db):
    await poll(db, NWS, [alert()], snapshot=True)
    await poll(db, NWS, minute=1, snapshot=True)
    await poll(db, NWS, [alert()], 2, snapshot=True)
    assert len(await current(db)) == 1 and len(await sql(db, "SELECT * FROM normalized_observations")) == 2
    assert (await current(db))[0]["observed_at"] == NOW


async def test_r3_r5_protected_unavailable_biological_record_reappears(db):
    r = observation()
    await poll(db, INATURALIST, [r])
    await poll(db, INATURALIST, minute=1, unavailable=[r["uuid"]])
    await poll(db, INATURALIST, [r], 2)
    rows = await normals(db)
    assert len(rows) == 2 and rows[0]["superseded_at"] and rows[1]["superseded_at"] is None
    assert all(n["sensitive"] for n in rows) and not rows[1]["point"]
    assert rows[1]["observed_at"] == NOW and rows[1]["valid_until"] == rows[0]["valid_until"]


async def test_r4_r9_duplicates_reinstated_rejected_distinct(db):
    r = perimeter()
    await poll(db, WFIGS, [r], snapshot=True)
    await poll(db, WFIGS, [r], 1, snapshot=True)
    assert len(await sql(db, "SELECT * FROM normalized_observations")) == 1
    await poll(db, WFIGS, minute=2, snapshot=True)
    await poll(db, WFIGS, [r], 3, snapshot=True)
    await poll(db, WFIGS, [r], 1.5, snapshot=True, completed=NOW + timedelta(minutes=4))
    runs = await sql(db, "SELECT * FROM source_runs ORDER BY id")
    assert runs[1]["duplicates"] == 1 and runs[1]["reinstated"] == 0
    assert runs[3]["reinstated"] == 1 and runs[3]["duplicates"] == 0
    assert runs[4]["records_rejected"] == 0 and runs[4]["records_accepted"] == runs[4]["duplicates"] == 0
    assert runs[4]["context_payload"]["outcome_counts"]["ignored_out_of_order_poll"] == 1


async def test_r6_older_late_snapshot_cannot_resurrect_retirement(db):
    await poll(db, WFIGS, [perimeter()], snapshot=True)
    await poll(db, WFIGS, minute=2, snapshot=True)
    late = await poll(db, WFIGS, [perimeter()], 1, snapshot=True, completed=NOW + timedelta(minutes=3))
    assert not await current(db) and late.skipped[0][1] == "out_of_order_poll" and not late.rejected
    assert await safety(db, 3) == "unknown"


async def test_r6_older_empty_snapshot_cannot_clear_newer_active(db):
    await poll(db, WFIGS, [perimeter()], 2, snapshot=True)
    await poll(db, WFIGS, minute=1, snapshot=True, completed=NOW + timedelta(minutes=3))
    assert len(await current(db)) == 1 and await safety(db, 3) == "hold_candidate"


async def test_r7_incomplete_does_not_retire(db):
    await poll(db, WFIGS, [perimeter()], snapshot=True)
    await poll(db, WFIGS, minute=1, complete=False, snapshot=True)
    assert len(await current(db)) == 1 and await safety(db, 1) == "hold_candidate"


async def test_r8_explicit_cancel_then_later_fetch_of_stale_alert(db):
    await poll(db, NWS, [alert()], snapshot=True)
    await poll(
        db, NWS, [alert(2, messageType="Cancel", references=[{"identifier": "urn:test:1"}])], 1, snapshot=True
    )
    replay = await poll(db, NWS, [alert()], 2, snapshot=True)
    assert not await current(db) and replay.skipped[0][1] == "stale_reference_replay" and not replay.rejected
    row = (await sql(db, "SELECT * FROM raw_observations WHERE external_id='urn:test:1'"))[0]
    assert row["retirement_reason"] == "explicit_reference" and row["retirement_provider_updated_at"] == NOW


async def test_r8_legacy_cancel_payload_restores_missing_barrier(db):
    await poll(db, NWS, [alert()], snapshot=True)
    await poll(
        db, NWS, [alert(2, messageType="Cancel", references=[{"identifier": "urn:test:1"}])], 1, snapshot=True
    )
    async with db.engine.begin() as c:
        await c.execute(
            text(
                "UPDATE raw_observations SET retirement_provider_updated_at=NULL,retirement_reason='legacy_retired' WHERE external_id='urn:test:1'"
            )
        )
    await poll(db, NWS, [alert()], 2, snapshot=True)
    assert not await current(db)


@pytest.mark.parametrize("mode", ["failed", "partial", "stale", "no_complete_snapshot"])
async def test_r10_negative_safety_requires_current_successful_complete_evidence(db, mode):
    await poll(db, WFIGS, snapshot=True)
    if mode == "stale":
        assert await safety(db, 181) == "unknown"
    else:
        await poll(
            db,
            WFIGS,
            minute=1,
            complete=mode not in ("failed", "partial"),
            snapshot=mode != "no_complete_snapshot",
        )
        assert await safety(db, 1) == "unknown"


async def legacy_future_record(db):
    await poll(db, INATURALIST, [observation(subject="bear")])
    async with db.engine.begin() as c:
        await c.execute(text("UPDATE raw_observations SET provider_updated_at='2099-01-01T00:00:00Z'"))
        await c.execute(text("UPDATE normalized_observations SET provider_updated_at='2099-01-01T00:00:00Z'"))


async def test_t1_future_open_then_older_valid_obscured_protected(db):
    await legacy_future_record(db)
    await poll(
        db,
        INATURALIST,
        [observation(subject="bear", obscured=True, updated_at=(NOW + timedelta(minutes=1)).isoformat())],
        1,
    )
    rows = await normals(db)
    assert all(n["sensitive"] for n in rows) and not rows[-1]["point"]
    assert rows[-1]["provider_updated_at"] == NOW + timedelta(minutes=1)
    assert rows[0]["provider_updated_at"].year == 2099  # historical meaning preserved


async def test_t2_future_historical_watermark_does_not_freeze_valid_correction(db):
    await legacy_future_record(db)
    await poll(db, INATURALIST, [observation(updated_at=(NOW + timedelta(minutes=1)).isoformat())], 1)
    rows = await normals(db)
    assert len(rows) == 2 and rows[0]["superseded_at"] and rows[1]["subject_key"] == "Danaus plexippus"
    run = (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]
    assert run["context_payload"]["invalid_historical_versions"] == [observation()["uuid"]]


async def test_t2_new_future_provider_version_rejected_not_persisted(db):
    await poll(db, INATURALIST, [observation(updated_at="2099-01-01T00:00:00Z")])
    assert not await normals(db)
    await poll(db, INATURALIST, [observation()], 1)
    assert len(await normals(db)) == 1


async def test_t2_identical_legitimate_fact_replaces_invalid_historical_native_stamp(db):
    await legacy_future_record(db)
    await poll(db, INATURALIST, [observation(subject="bear")], 1)
    rows = await normals(db)
    assert len(rows) == 2 and rows[0]["superseded_at"]
    assert rows[1]["provider_updated_at"] == NOW and rows[0]["provider_updated_at"].year == 2099


async def test_t3_older_open_cannot_downgrade_or_regress_fields(db):
    await poll(
        db,
        INATURALIST,
        [observation(subject="bear", obscured=True, updated_at=(NOW + timedelta(minutes=1)).isoformat())],
        1,
    )
    batch = await poll(db, INATURALIST, [observation()], 2)
    row = (await normals(db))[0]
    assert row["sensitive"] and row["subject_key"] == "Ursus americanus" and not row["point"]
    assert batch.skipped[0][1] == "stale_provider_update" and not batch.rejected


async def test_t4_future_forecast_valid_period_allowed_native_issue_now(db):
    period = forecast(
        startTime=(NOW + timedelta(days=3)).isoformat(),
        endTime=(NOW + timedelta(days=3, hours=1)).isoformat(),
    )
    batch = Batch(received=1, records=[nws.forecast(period, NOW)], provider_updated_at=NOW)
    await persist(db, NWS, batch, NOW, NOW)
    assert len(await current(db)) == 1 and not batch.rejected


async def test_t5_one_future_clock_isolated_among_many(db):
    values = [observation(i) for i in range(1, 21)]
    values[4]["updated_at"] = "2099-01-01T00:00:00Z"
    batch = await poll(db, INATURALIST, values)
    assert len(await current(db)) == 19 and batch.rejected == [(values[4]["uuid"], "future_provider_update")]
    run = (await sql(db, "SELECT * FROM source_runs"))[0]
    assert (
        run["provider_updated_at"] == NOW and run["records_accepted"] == 19 and run["records_rejected"] == 1
    )


async def test_t6_older_privacy_only_immediately_redacts_current_and_history(db):
    await poll(
        db,
        INATURALIST,
        [
            observation(i, subject="bear", updated_at=(NOW + timedelta(minutes=30)).isoformat())
            for i in range(1, 4)
        ],
    )
    initial = await generate(db)
    assert initial.clusters and not initial.clusters[0].redacted
    await poll(db, INATURALIST, [observation(subject="bear", obscured=True)], 1)
    value = await read(db, NOW + timedelta(minutes=1))
    assert value.clusters[0].redacted and value.clusters[0].metrics is None
    row = (await normals(db))[0]
    assert row["sensitive"] and not row["point"] and row["provider_updated_at"] == NOW + timedelta(minutes=30)
    assert row["superseded_at"] is None and row["source_metadata"]["coordinates_obscured"] is False
    run = (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]
    assert run["context_payload"]["protection_events"] and run["records_rejected"] == 0
    assert run["context_payload"]["outcome_counts"]["skipped_stale_version"] == 1


async def test_t7_older_privacy_update_never_reactivates_retired_fact(db):
    r = observation(updated_at=(NOW + timedelta(minutes=30)).isoformat())
    await poll(db, INATURALIST, [r])
    await poll(db, INATURALIST, minute=1, unavailable=[r["uuid"]])
    await poll(db, INATURALIST, [observation(obscured=True)], 2)
    assert not await current(db) and (await normals(db))[0]["sensitive"]


async def test_t7_out_of_order_privacy_still_elevates_without_other_changes(db):
    await poll(db, INATURALIST, [observation(subject="bear")], 2)
    await poll(db, INATURALIST, [observation(obscured=True)], 1, completed=NOW + timedelta(minutes=3))
    row = (await normals(db))[0]
    assert row["sensitive"] and row["subject_key"] == "Ursus americanus" and not row["point"]
    assert row["superseded_at"] is None


async def test_t1_future_rejected_privacy_still_protects_without_regression(db):
    await poll(db, INATURALIST, [observation(subject="bear")])
    batch = await poll(db, INATURALIST, [observation(obscured=True, updated_at="2099-01-01T00:00:00Z")], 1)
    row = (await normals(db))[0]
    assert batch.rejected[0][1] == "future_provider_update"
    assert row["sensitive"] and not row["point"] and row["subject_key"] == "Ursus americanus"
    assert row["provider_updated_at"] == NOW and row["superseded_at"] is None


async def test_cadence_new_source_poll_marks_watch_outdated_without_m1_rerun(db):
    await poll(db, INATURALIST, [observation(i, subject="bear") for i in range(1, 4)])
    await generate(db)
    before = await calibration(db, NOW)
    assert before["items"][0]["level"] == "developing_watch"
    assessments = await sql(db, "SELECT id FROM assessment_runs")
    await poll(db, INATURALIST, [observation(4, subject="bear")], 1)
    # Preserve the accepted short source-change grace; do not rewrite M2.
    after = await calibration(db, NOW + timedelta(minutes=1, seconds=1) + db.grace)
    assert after["pattern_analysis_state"] == "outdated" and after["items"][0]["level"] == "signal"
    assert await sql(db, "SELECT id FROM assessment_runs") == assessments


async def test_t7_older_unavailable_protects_without_retiring_current(db):
    record = observation(subject="bear")
    await poll(db, INATURALIST, [record], 2)
    await poll(db, INATURALIST, minute=1, unavailable=[record["uuid"]], completed=NOW + timedelta(minutes=3))
    row = (await normals(db))[0]
    assert row["sensitive"] and not row["point"] and row["superseded_at"] is None
    assert row["subject_key"] == "Ursus americanus" and row["provider_updated_at"] == NOW
    run = (await sql(db, "SELECT * FROM source_runs ORDER BY id"))[-1]
    assert run["context_payload"]["protection_events"][0]["basis"] == "public_unavailable"


async def test_t6_protection_provenance_survives_accepted_correction_and_retention(db):
    from pec.retention import sweep

    await poll(db, INATURALIST, [observation(updated_at=(NOW + timedelta(minutes=30)).isoformat())])
    await poll(db, INATURALIST, [observation(obscured=True)], 1)
    protected_run = (await sql(db, "SELECT privacy_source_run_id FROM raw_observations"))[0][
        "privacy_source_run_id"
    ]
    assert protected_run is not None
    await poll(db, INATURALIST, [observation(updated_at=(NOW + timedelta(minutes=40)).isoformat())], 40)
    raw = (await sql(db, "SELECT * FROM raw_observations"))[0]
    assert raw["privacy_source_run_id"] == protected_run and (await current(db))[0]["sensitive"]
    await db.pattern_transaction(lambda c: sweep(c, NOW + timedelta(days=200)), write=True)
    assert any(r["id"] == protected_run for r in await sql(db, "SELECT * FROM source_runs"))


async def test_f3_real_production_pool_exhaustion_does_not_block_backoff(db):
    state = State(NOW + timedelta(hours=2), 2)
    connections = [await db.engine.connect() for _ in range(5)]
    try:
        await asyncio.wait_for(backoff.save(db, "inaturalist", state), 2)
        assert await asyncio.wait_for(backoff.load(db, "inaturalist", NOW), 2) == state
    finally:
        await asyncio.gather(*(c.close() for c in connections))
    restarted = Database(Settings(URL, "test-only-" + "a" * 40))
    try:
        assert await backoff.load(restarted, "inaturalist", NOW) == state
    finally:
        await restarted.close()


async def test_concurrent_newer_withdrawal_then_late_response(db):
    await poll(db, WFIGS, [perimeter()], snapshot=True)
    newer_committed = asyncio.Event()

    async def newer():
        await poll(db, WFIGS, minute=2, snapshot=True)
        newer_committed.set()

    async def older():
        await newer_committed.wait()
        await poll(db, WFIGS, [perimeter()], 1, snapshot=True, completed=NOW + timedelta(minutes=3))

    await asyncio.gather(newer(), older())
    assert not await current(db) and await safety(db, 3) == "unknown"


async def test_live_fire_safety_updates_without_new_m1_or_m2(db):
    assert not await sql(db, "SELECT * FROM assessment_runs")
    await poll(db, WFIGS, [perimeter()], snapshot=True)
    assert await safety(db) == "hold_candidate"
    await poll(db, WFIGS, minute=1, snapshot=True)
    assert await safety(db, 1) == "no_intersection"
    assert not await sql(db, "SELECT * FROM assessment_runs")
