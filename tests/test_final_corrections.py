"""Final F1-F14: real PostgreSQL backend locks and conservative analytical repairs."""
import asyncio
import time
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.ingestion import collect_fixture
from pec.patterns import clustering, engine, episodes
from pec.patterns.policy import POLICIES
from test_database import DATA, NOW
from test_patterns_database import (
    BEAR, EAGLE, data, db as database_fixture, publish, records, record,
    pytestmark as database_marks, sql,
)

db=database_fixture
pytestmark=database_marks


async def stalled_finish(db,monkeypatch):
    await publish(db,[*DATA["sightings"],*records(6)])
    entered=asyncio.Event()
    original=episodes.assign
    observed={}
    async def slow(c,*args):
        observed["pid"]=(await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        observed["statement"]=(await c.execute(text("SHOW statement_timeout"))).scalar_one()
        observed["lock"]=(await c.execute(text("SHOW lock_timeout"))).scalar_one()
        entered.set()
        await c.execute(text("SELECT pg_sleep(6)"))
        return await original(c,*args)
    monkeypatch.setattr(episodes,"assign",slow)
    db.timeout=3
    base=await db.generate(data(1))
    await asyncio.wait_for(entered.wait(),2)
    return base,observed


async def assert_healthy(db):
    await db.wait_for_patterns()
    assert db.engine.pool.checkedout()==db.pattern_engine.pool.checkedout()==0
    await db.ready()
    assert not db.failed


async def test_f1_slow_locked_finish_cannot_block_new_high_wind_m1(db,monkeypatch,record_property):
    base,observed=await stalled_finish(db,monkeypatch)
    wind={**DATA,"now":(NOW+timedelta(hours=2)).isoformat(),"alerts":[{
        "event":"High Wind Warning","onset":NOW.isoformat(),
        "ends":(NOW+timedelta(days=1)).isoformat(),"same":["006079"]}]}
    db.patterns_mode="off"
    await collect_fixture(db,wind)
    start=time.perf_counter()
    result=await db.generate(wind)
    record_property("m1_publication_seconds",time.perf_counter()-start)
    record_property("m1_deadline_seconds",db.timeout)
    assert result["status"]=="published" and result["assessment_id"]!=base["assessment_id"]
    product=await db.opportunities(NOW+timedelta(hours=2))
    assert product.assessment_state=="complete" and product.items[0].safety_state=="unsafe"
    assert "High Wind" in product.items[0].safety_summary
    await assert_healthy(db)
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=base["assessment_id"]))[0]["status"]=="failed"


async def test_f2_server_lock_timeout_yields_to_m1_publication(db,monkeypatch):
    await publish(db,records(3))
    prepared,release,locked=asyncio.Event(),asyncio.Event(),asyncio.Event()
    original_prepare=episodes.prepare
    async def pause(*args,**kwargs):
        plan=await original_prepare(*args,**kwargs)
        prepared.set()
        await release.wait()
        return plan
    monkeypatch.setattr(episodes,"prepare",pause)
    base=await db.generate(data(1))
    await asyncio.wait_for(prepared.wait(),2)
    from pec import publication
    original_inputs=publication.stored_inputs
    async def hold(c,*args):
        locked.set()
        await c.execute(text("SELECT pg_sleep(1.2)"))
        return await original_inputs(c,*args)
    monkeypatch.setattr(publication,"stored_inputs",hold)
    db.patterns_mode="off"
    db.timeout=3
    m1=asyncio.create_task(db.generate(data(2)))
    await asyncio.wait_for(locked.wait(),2)
    release.set()
    result=await m1
    assert result["status"]=="published"
    await assert_healthy(db)
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=base["assessment_id"]))[0]["status"]=="failed"


async def test_f3_server_statement_bound_aborts_and_releases_pointer(db,monkeypatch):
    base,observed=await stalled_finish(db,monkeypatch)
    assert observed["statement"]=="750ms" and observed["lock"]=="500ms"
    await db.wait_for_patterns()
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=base["assessment_id"]))[0]["status"]=="failed"
    assert not await sql(db,"SELECT pid FROM pg_stat_activity WHERE pid=:pid AND state<>'idle'",pid=observed["pid"])
    async with db.engine.begin() as c:
        await c.execute(text("SET LOCAL lock_timeout='200ms'"))
        await c.execute(text("SELECT assessment_run_id FROM assessment_current WHERE id=1 FOR UPDATE"))
    await assert_healthy(db)


async def test_f4_no_shadow_pool_leak_after_server_timeout(db,monkeypatch):
    await stalled_finish(db,monkeypatch)
    await assert_healthy(db)
    async def ping(c):
        assert (await c.execute(text("SELECT 1"))).scalar_one()==1
    await db.pattern_transaction(ping)
    assert db.pattern_engine.pool.checkedout()==0


async def test_f5_cancelled_error_propagates_after_bounded_cleanup(db,monkeypatch):
    await publish(db,records(3))
    entered=asyncio.Event()
    async def pause(*args):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(engine,"compute",pause)
    generated=await db.generate(data(1))
    await asyncio.wait_for(entered.wait(),2)
    task=next(iter(db._pattern_tasks))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await sql(db,"SELECT status,error_code FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=generated["assessment_id"]))[0]=={"status":"failed","error_code":"shadow_cancelled"}
    await assert_healthy(db)


def bear_bridge():
    return [*records(6),*[record(i,longitude=-120.5+(i-5)*0.0298) for i in range(6,11)]]


async def test_f6_dense_bear_core_survives_sparse_bridge(db):
    first=await publish(db,records(6))
    second=await publish(db,bear_bridge(),hour=1)
    assert len(second.clusters)==1 and second.clusters[0].metrics.independent_report_count==6
    assert second.items[0].episode_key==first.items[0].episode_key
    assert second.items[0].state=="qualified"
    rejected=second.coherence_rejections[0]
    assert rejected.metrics.candidate_observation_count==rejected.metrics.independent_report_count==11
    assert rejected.fallback_attempted and rejected.fallback_eps_meters==1000
    assert rejected.fallback_result=="recovered" and rejected.metrics.recovered_cluster_count==1


async def test_f7_pure_sparse_chain_has_no_false_cluster(db):
    result=await publish(db,[record(i,longitude=-120.5+i*0.0298) for i in range(7)])
    assert not result.clusters and not result.items and not result.preview_opportunities
    assert result.coherence_rejections[0].fallback_result=="no_qualifying_core"
    assert result.coherence_rejections[0].metrics.recovered_cluster_count==0


async def test_f8_debug_and_snapshot_distinguish_coherence_rejected(db):
    await publish(db,records(6))
    result=await publish(db,[record(i,longitude=-120.5+i*0.0298) for i in range(7)],hour=1)
    assert result.items[0].transition=="coherence_rejected"
    assert result.coherence_rejections[0].state=="coherence_rejected"
    assert (await sql(db,"SELECT transition_code FROM pattern_episode_snapshots WHERE assessment_run_id=:aid",
                      aid=result.assessment_id))[0]["transition_code"]=="coherence_rejected"
    assert "centroid" not in result.model_dump_json() and "longitude" not in result.model_dump_json()


async def test_f9_unknown_animal_count_cannot_satisfy_count_gate(db):
    policy=replace(BEAR,trigger="COUNT_THRESHOLD",count_requirement=1)
    result=await publish(db,records(3),policies=(policy,))
    assert not result.clusters and not result.items
    with pytest.raises(ValueError):
        replace(policy,count_requirement=0)


def origin_claim(**changes):
    return record(1,provider="fixture_mirror_a",origin_namespace="fixture_observations",
                  origin_external_id="report-0",**changes)


async def test_f10_incompatible_claimed_taxon_does_not_collapse(db,caplog):
    await publish(db,[record(0),origin_claim(scientific_name=EAGLE.subject)])
    groups=await sql(db,"SELECT report_group_id FROM observation_report_group_members WHERE superseded_at IS NULL")
    assert len({row["report_group_id"] for row in groups})==2
    assert (await sql(db,"SELECT origin_identity_status FROM normalized_observations WHERE subject_key=:subject",
                      subject=EAGLE.subject))[0]["origin_identity_status"]=="origin_identity_mismatch"
    assert "origin_identity_mismatch" in caplog.text and EAGLE.subject not in caplog.text


async def test_f11_incompatible_claimed_observation_time_does_not_collapse(db):
    await publish(db,[record(0),origin_claim(observed_at=(NOW-timedelta(days=2)).isoformat())])
    assert len({row["report_group_id"] for row in await sql(db,
        "SELECT report_group_id FROM observation_report_group_members WHERE superseded_at IS NULL")})==2
    assert len(await sql(db,"SELECT id FROM normalized_observations WHERE origin_identity_status='origin_identity_mismatch'"))==1


async def test_f12_consistent_explicit_origin_still_collapses(db):
    result=await publish(db,[record(0),origin_claim()],policies=(replace(BEAR,min_independent_reports=1,minimum_observations=1),))
    assert result.clusters[0].metrics.independent_report_count==1
    assert result.clusters[0].metrics.independent_source_count==2
    assert len(await sql(db,"SELECT id FROM normalized_observations WHERE origin_identity_status='explicit_verified'"))==1


async def test_f13_sql_loader_excludes_old_history_before_python_admission(db):
    await collect_fixture(db,data(sightings=[*records(3),record(99,observed_at=(NOW-timedelta(days=8)).isoformat())]))
    async with db.engine.begin() as c:
        from pec.patterns.identity import reconcile
        await reconcile(c,NOW)
        rows,_,_=await clustering.load_inputs(c,NOW,POLICIES)
    assert len(await sql(db,"SELECT id FROM normalized_observations"))==4
    assert len(rows)==3 and all(row["observed_at"]>=NOW-timedelta(days=4) for row in rows)


async def test_f14_default_m1_latency_bounded_while_server_finish_stalls(db,monkeypatch,record_property):
    await stalled_finish(db,monkeypatch)
    db.patterns_mode="off"
    start=time.perf_counter()
    result=await db.generate(data(2))
    elapsed=time.perf_counter()-start
    record_property("m1_publication_seconds",elapsed)
    record_property("m1_deadline_seconds",db.timeout)
    assert db.timeout==3 and elapsed<3 and result["status"]=="published"
    await assert_healthy(db)


async def test_sensitive_coherence_diagnostics_never_disclose_candidate_metrics(db):
    result=await publish(db,[{**row,"private_location":True} for row in bear_bridge()])
    assert result.coherence_rejections[0].redacted and result.coherence_rejections[0].metrics is None
    assert not result.preview_opportunities
    encoded=result.model_dump_json()
    assert "-120.5" not in encoded and '"candidate_radius_meters"' not in encoded



async def test_server_limits_follow_smaller_shadow_finish_budget(db,monkeypatch):
    await publish(db,records(3))
    limits={}
    async def stall(c,*args):
        for setting in ("lock_timeout","statement_timeout","transaction_timeout"):
            limits[setting]=(await c.execute(text("SHOW "+setting))).scalar_one()
        await c.execute(text("SELECT pg_sleep(1)"))
    monkeypatch.setattr(episodes,"assign",stall)
    db.timeout=3
    db.pattern_timeout=0.2
    generated=await db.generate(data(1))
    await db.wait_for_patterns()
    assert limits=={"lock_timeout":"100ms","statement_timeout":"150ms","transaction_timeout":"180ms"}
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=generated["assessment_id"]))[0]["status"]=="failed"
    await assert_healthy(db)


async def test_authoritative_arrival_rehomes_incompatible_earlier_mirror(db):
    await collect_fixture(db,data(sightings=[origin_claim(scientific_name=EAGLE.subject)]))
    from pec.patterns.identity import reconcile
    await db.pattern_transaction(lambda c: reconcile(c,NOW),write=True,repeatable=True)
    before=await sql(db,"SELECT id,report_group_id FROM observation_report_group_members")
    await collect_fixture(db,data(1,[record(0)]))
    await db.pattern_transaction(lambda c: reconcile(c,NOW+timedelta(hours=1)),write=True,repeatable=True)
    links=await sql(db,"SELECT report_group_id FROM observation_report_group_members WHERE superseded_at IS NULL")
    assert len({row["report_group_id"] for row in links})==2
    assert (await sql(db,"SELECT superseded_at FROM observation_report_group_members WHERE id=:id",id=before[0]["id"]))[0]["superseded_at"] is not None


async def test_invalidated_episode_plan_is_superseded_without_registry_mutation(db,monkeypatch):
    await publish(db,records(3))
    original=episodes.prepare
    async def change(c,*args,**kwargs):
        plan=await original(c,*args,**kwargs)
        async with db.engine.begin() as other:
            await other.execute(text("UPDATE pattern_episodes SET compatibility_key='external-correction'"))
        return plan
    monkeypatch.setattr(episodes,"prepare",change)
    result=await db.generate(data(1))
    await db.wait_for_patterns()
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=result["assessment_id"]))[0]["status"]=="superseded"
    assert not await sql(db,"SELECT * FROM pattern_episode_snapshots WHERE assessment_run_id=:aid",aid=result["assessment_id"])



@pytest.mark.parametrize("trigger,changes",[
    ("COUNT_THRESHOLD",{"count_requirement":1}),
    ("BEHAVIOR_REQUIRED",{"behaviors":("fishing",)}),
])
async def test_fallback_reapplies_required_evidence_gates(db,trigger,changes):
    policy=replace(BEAR,trigger=trigger,**changes)
    result=await publish(db,bear_bridge(),policies=(policy,))
    assert not result.clusters and not result.items
    assert result.coherence_rejections[0].fallback_result=="no_qualifying_core"


async def test_no_configured_fallback_never_invents_epsilon(db):
    result=await publish(db,bear_bridge(),policies=(replace(BEAR,coherence_fallback_eps_meters=None),))
    assert not result.clusters and result.coherence_rejections[0].fallback_result=="not_configured"
    assert not result.coherence_rejections[0].fallback_attempted


async def test_fallback_never_performs_a_third_pass(db):
    from sqlalchemy import event as sql_event
    statements=[]
    def inspect(c,cursor,statement,params,context,many):
        if "ST_ClusterDBSCAN" in statement:
            statements.append(statement)
    sql_event.listen(db.pattern_engine.sync_engine,"before_cursor_execute",inspect)
    try:
        # A stricter second pass still chains these points and fails diameter.
        result=await publish(db,[record(i,longitude=-120.5+i*0.018) for i in range(9)],
                             policies=(replace(BEAR,coherence_fallback_eps_meters=2000),))
        assert not result.clusters and len(statements)==2
        assert result.coherence_rejections[0].fallback_result=="no_qualifying_core"
    finally:
        sql_event.remove(db.pattern_engine.sync_engine,"before_cursor_execute",inspect)


async def test_coherence_diagnostics_obey_immediate_sensitive_raise(db):
    from pec.patterns.api import read
    first=await publish(db,bear_bridge())
    assert first.coherence_rejections[0].metrics is not None
    await collect_fixture(db,data(1,[{**row,"private_location":True} for row in bear_bridge()]))
    result=await read(db,NOW+timedelta(hours=1))
    assert result.coherence_rejections[0].redacted and result.coherence_rejections[0].metrics is None
