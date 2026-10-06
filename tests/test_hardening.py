"""Real PostGIS hardening regressions P1-P7, B1-B4 and C1-C5."""
import asyncio
import time
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import text

from pec.ingestion import collect_fixture
from pec.patterns import identity
from test_database import NOW
from test_final_corrections import bear_bridge, origin_claim
from test_patterns_database import BEAR, EAGLE, data, db as database_fixture, publish, record, records, sql
from test_patterns_database import pytestmark as database_marks

db=database_fixture
pytestmark=database_marks


async def reconcile(db, hour=0):
    await db.pattern_transaction(lambda c: identity.reconcile(c,NOW+timedelta(hours=hour)),
                                 write=True,repeatable=True)


async def current_groups(db):
    return await sql(db,"""SELECT n.id,n.subject_key,n.observed_at,n.origin_identity_status,
        s.key AS provider,m.report_group_id,m.id AS mid FROM normalized_observations n
        JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
        JOIN observation_report_group_members m ON m.normalized_observation_id=n.id
        WHERE n.superseded_at IS NULL AND m.superseded_at IS NULL ORDER BY s.key,n.id""")


async def measured_collect(db, mode, record_property):
    assert db.timeout==3
    db.patterns_mode=mode
    start=time.perf_counter()
    await collect_fixture(db,data(sightings=records(500)))
    seconds=time.perf_counter()-start
    record_property("collection_seconds",seconds)
    record_property("collection_deadline_seconds",db.timeout)
    assert seconds<3
    assert len(await sql(db,"SELECT id FROM normalized_observations WHERE superseded_at IS NULL"))==500
    assert (await sql(db,"SELECT records_accepted FROM source_runs JOIN sources ON sources.id=source_id WHERE sources.key='fixture_observations'"))[0]["records_accepted"]==500


async def test_p1_500_records_off_default_collection_deadline(db,record_property):
    await measured_collect(db,"off",record_property)


async def test_p2_500_records_shadow_default_collection_deadline(db,record_property):
    await measured_collect(db,"shadow",record_property)
    # Reconciliation belongs to a pattern run, not collection or its deadline.
    assert not await sql(db,"SELECT id FROM observation_report_group_members")


async def test_p3_enrichment_failure_cannot_rollback_m1_collection(db,monkeypatch):
    db.patterns_mode="shadow"
    async def fail(*args):
        raise RuntimeError("injected enrichment failure")
    monkeypatch.setattr(identity,"reconcile",fail)
    await collect_fixture(db,data(sightings=records(3)))
    generated=await db.generate(data())
    await db.wait_for_patterns()
    assert generated["status"]=="published" and not db.failed
    assert len(await sql(db,"SELECT id FROM normalized_observations WHERE superseded_at IS NULL"))==3
    assert (await sql(db,"SELECT status,error_code,input_fingerprint FROM pattern_generation_runs"))[0]=={
        "status":"failed","error_code":"shadow_failed","input_fingerprint":None}
    assert (await sql(db,"SELECT records_accepted FROM source_runs JOIN sources ON sources.id=source_id WHERE sources.key='fixture_observations'"))[0]["records_accepted"]==3


async def test_p4_slow_enrichment_does_not_delay_collection(db,monkeypatch):
    entered,release=asyncio.Event(),asyncio.Event()
    original=identity.reconcile
    async def slow(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    monkeypatch.setattr(identity,"reconcile",slow)
    db.patterns_mode="shadow"
    await collect_fixture(db,data(sightings=records(3)))
    await db.generate(data())
    await asyncio.wait_for(entered.wait(),2)
    try:
        assert db.timeout==3
        await asyncio.wait_for(collect_fixture(db,data(1,records(500))),3)
        assert not release.is_set() and not db.failed
    finally:
        release.set()
        await db.wait_for_patterns()


async def test_p5_off_collection_has_no_m2_sql_or_behavior_resolution(db,monkeypatch):
    from sqlalchemy import event
    statements=[]
    def capture(c,cursor,statement,parameters,context,executemany):
        statements.append(statement)
    def forbidden(*args,**kwargs):
        raise AssertionError("M2 behavior resolution entered M1 collection")
    monkeypatch.setattr(identity,"behavior_codes",forbidden)
    event.listen(db.engine.sync_engine,"before_cursor_execute",capture)
    try:
        await collect_fixture(db,data(sightings=records(10,behavior="feeding")))
    finally:
        event.remove(db.engine.sync_engine,"before_cursor_execute",capture)
    assert db.patterns_mode=="off"
    assert not any("observation_report_" in query or "normalized_observation_behaviors" in query for query in statements)
    assert not await sql(db,"SELECT * FROM observation_report_groups")
    assert not await sql(db,"SELECT * FROM normalized_observation_behaviors")


async def test_p6_corrections_while_enrichment_lags_converge_current_assertions(db):
    await collect_fixture(db,data(sightings=[record(0,behavior="feeding"),origin_claim()]))
    await collect_fixture(db,data(1,[record(0,behavior="fishing",observed_at=(NOW+timedelta(hours=3)).isoformat())]))
    await collect_fixture(db,data(2,[record(0,behavior="rut")]))
    assert not await sql(db,"SELECT * FROM observation_report_group_members")
    await reconcile(db,2)
    current=await current_groups(db)
    assert len(current)==2 and len({r["report_group_id"] for r in current})==1
    assert not await sql(db,"""SELECT m.id FROM observation_report_group_members m
        JOIN normalized_observations n ON n.id=m.normalized_observation_id
        WHERE m.superseded_at IS NULL AND n.superseded_at IS NOT NULL""")
    assert [r["behavior_code"] for r in await sql(db,"""SELECT b.behavior_code FROM normalized_observation_behaviors b
        JOIN normalized_observations n ON n.id=b.normalized_observation_id
        JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
        WHERE n.superseded_at IS NULL AND s.key='fixture_observations' ORDER BY behavior_code""")]==["presence","rut"]


async def test_p7_large_collection_then_m1_generation_while_m2_catches_up(db,monkeypatch):
    entered,release=asyncio.Event(),asyncio.Event()
    original=identity.reconcile
    async def slow(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    monkeypatch.setattr(identity,"reconcile",slow)
    db.patterns_mode="shadow"
    await collect_fixture(db,data(sightings=records(500)))
    result=await db.generate(data())
    await asyncio.wait_for(entered.wait(),2)
    try:
        assert result["status"]=="published" and not db.failed and db.timeout==3
        next_result=await db.generate(data(1))
        assert next_result["status"]=="published"
        assert (await db.opportunities(NOW+timedelta(hours=1))).assessment_state=="complete"
    finally:
        release.set()
        await db.wait_for_patterns()


async def test_b1_unrelated_rejected_chain_cannot_label_aging_episode(db):
    policy=replace(BEAR,temporal_window_seconds=3600)
    first=await publish(db,records(6),policies=(policy,))
    far=[record(100+i,longitude=-118.8+i*0.0298,observed_at=(NOW+timedelta(hours=2)).isoformat()) for i in range(7)]
    second=await publish(db,far,hour=2)
    assert second.coherence_rejections
    episode=next(e for e in second.items if e.episode_key==first.items[0].episode_key)
    assert episode.transition=="unsupported"


async def test_b2_rejected_candidate_with_prior_reports_labels_own_episode(db):
    first=await publish(db,records(6))
    second=await publish(db,[record(i,longitude=-120.5+i*0.0298) for i in range(7)],hour=1)
    assert second.items[0].episode_key==first.items[0].episode_key
    assert second.items[0].transition=="coherence_rejected"


async def test_b3_only_related_episode_receives_coherence_rejection(db):
    policy=replace(BEAR,temporal_window_seconds=3600)
    far=records(6)
    far=[{**r,"external_id":f"far-{i}","longitude":-118.8+i*0.0001} for i,r in enumerate(far)]
    await publish(db,[*records(6),*far],policies=(policy,))
    second=await publish(db,[{**r,"longitude":-118.8+i*0.0298,
        "observed_at":(NOW+timedelta(hours=2)).isoformat()} for i,r in enumerate(far)],hour=2)
    transitions=[row["transition_code"] for row in await sql(db,
        "SELECT transition_code FROM pattern_episode_snapshots WHERE assessment_run_id=:aid",aid=second.assessment_id)]
    assert sorted(transitions)==["coherence_rejected","unsupported"]


async def test_b4_recovered_core_retains_supported_episode(db):
    first=await publish(db,records(6))
    second=await publish(db,bear_bridge(),hour=1)
    assert second.items[0].episode_key==first.items[0].episode_key
    assert second.items[0].transition=="continued" and second.items[0].metrics.independent_report_count==6


async def test_c1_canonical_time_correction_recollapses_without_mirror_redelivery(db):
    mirror=origin_claim(observed_at=(NOW-timedelta(days=2)).isoformat())
    await publish(db,[record(0),mirror])
    before=await current_groups(db)
    mirror_id=next(row["id"] for row in before if row["provider"]=="fixture_mirror_a")
    old_mid=next(row["mid"] for row in before if row["id"]==mirror_id)
    assert len({r["report_group_id"] for r in before})==2
    await collect_fixture(db,data(1,[record(0,observed_at=mirror["observed_at"])]))
    await reconcile(db,1)
    after=await current_groups(db)
    assert len({r["report_group_id"] for r in after})==1
    assert next(row["id"] for row in after if row["provider"]=="fixture_mirror_a")==mirror_id
    assert (await sql(db,"SELECT superseded_at FROM observation_report_group_members WHERE id=:id",id=old_mid))[0]["superseded_at"] is not None
    generated=await db.generate(data(1))
    await db.wait_for_patterns()
    assert (await sql(db,"SELECT status,input_fingerprint FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=generated["assessment_id"]))[0]["status"]=="published"
    assert (await sql(db,"SELECT independent_report_count FROM observation_clusters WHERE assessment_run_id=:aid",
                      aid=generated["assessment_id"]))[0]["independent_report_count"]==1


async def test_c2_canonical_still_incompatible_keeps_mirror_independent(db):
    await publish(db,[record(0),origin_claim(observed_at=(NOW-timedelta(days=2)).isoformat())])
    await collect_fixture(db,data(1,[record(0,observed_at=(NOW+timedelta(minutes=20)).isoformat())]))
    await reconcile(db,1)
    assert len({r["report_group_id"] for r in await current_groups(db)})==2


async def test_c3_canonical_becomes_incompatible_splits_valid_mirror(db):
    await publish(db,[record(0),origin_claim()])
    assert len({r["report_group_id"] for r in await current_groups(db)})==1
    history=await sql(db,"SELECT cluster_id,normalized_observation_id,report_group_id,membership_id FROM cluster_members ORDER BY cluster_id,normalized_observation_id")
    await collect_fixture(db,data(1,[record(0,observed_at=(NOW+timedelta(days=2)).isoformat())]))
    await reconcile(db,1)
    assert len({r["report_group_id"] for r in await current_groups(db)})==2
    assert history==await sql(db,"SELECT cluster_id,normalized_observation_id,report_group_id,membership_id FROM cluster_members ORDER BY cluster_id,normalized_observation_id")


async def test_c4_canonical_subject_correction_retries_rejected_claim(db):
    await publish(db,[record(0),origin_claim(scientific_name=EAGLE.subject)])
    assert len({r["report_group_id"] for r in await current_groups(db)})==2
    await collect_fixture(db,data(1,[record(0,subject=EAGLE.subject)]))
    await reconcile(db,1)
    assert len({r["report_group_id"] for r in await current_groups(db)})==1


async def test_c5_no_explicit_claim_never_fuzzily_collapses(db):
    await publish(db,[record(0),record(1,provider="fixture_mirror_a")])
    await collect_fixture(db,data(1,[record(0,longitude=-120.5+0.0001)]))
    await reconcile(db,1)
    assert len({r["report_group_id"] for r in await current_groups(db)})==2


async def test_enrichment_batch_query_count_and_idempotent_history(db):
    from sqlalchemy import event
    await collect_fixture(db,data(sightings=records(500)))
    queries=[]
    def capture(*args):
        queries.append(args[2])
    event.listen(db.pattern_engine.sync_engine,"before_cursor_execute",capture)
    try:
        await reconcile(db)
    finally:
        event.remove(db.pattern_engine.sync_engine,"before_cursor_execute",capture)
    assert len(queries)<=10
    before=await sql(db,"SELECT * FROM observation_report_group_members ORDER BY id")
    await reconcile(db)
    assert before==await sql(db,"SELECT * FROM observation_report_group_members ORDER BY id")

async def test_enrichment_backend_stall_releases_shared_assertion_for_m1_correction(db,monkeypatch):
    entered=asyncio.Event()
    original=identity.reconcile
    async def slow(c,*args):
        await original(c,*args)
        entered.set()
        await c.execute(text("SELECT pg_sleep(6)"))
    monkeypatch.setattr(identity,"reconcile",slow)
    db.patterns_mode="shadow"
    await collect_fixture(db,data(sightings=records(3)))
    await db.generate(data())
    await asyncio.wait_for(entered.wait(),2)
    start=time.perf_counter()
    await collect_fixture(db,data(1,records(3,behavior="feeding")))
    assert time.perf_counter()-start<db.timeout==3
    await db.wait_for_patterns()
    assert not db.failed
    assert not await sql(db,"SELECT * FROM observation_report_group_members")
    assert not await sql(db,"SELECT * FROM pattern_generation_sources")
    assert (await sql(db,"SELECT status,input_fingerprint FROM pattern_generation_runs"))[0]=={
        "status":"failed","input_fingerprint":None}
    assert len(await sql(db,"SELECT * FROM normalized_observations WHERE superseded_at IS NULL AND behavior='feeding'"))==3

async def test_retained_explicit_claim_retries_after_raw_body_pruning(db):
    from pec.retention import sweep
    mirror=origin_claim(observed_at=(NOW-timedelta(days=100)).isoformat(),
                        notes="bulk provider body to remove")
    await collect_fixture(db,data(sightings=[record(0),mirror]))
    await reconcile(db)
    assert len({r["report_group_id"] for r in await current_groups(db)})==2
    async with db.engine.begin() as c:
        result=await sweep(c,NOW)
    assert result["payloads_redacted"]==1
    payload=(await sql(db,"SELECT raw_payload FROM raw_observations JOIN sources ON sources.id=source_id WHERE sources.key='fixture_mirror_a'"))[0]["raw_payload"]
    assert payload["origin_external_id"]=="report-0" and payload["_m2_retained_metadata"]
    assert "notes" not in payload and "scientific_name" not in payload
    async with db.engine.begin() as c:
        assert (await sweep(c,NOW))["payloads_redacted"]==0
    await collect_fixture(db,data(1,[record(0,observed_at=mirror["observed_at"])]))
    await reconcile(db,1)
    assert len({r["report_group_id"] for r in await current_groups(db)})==1
