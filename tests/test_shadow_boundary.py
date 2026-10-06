"""S1: real-DB failure, pool, deadline and publication-race isolation."""
import asyncio
import json
import math
import random
from datetime import timedelta

from sqlalchemy import text

from pec.ingestion import collect_fixture, ingest_fixture
from pec.patterns import clustering, engine
from pec.patterns.api import read
from test_database import DATA, NOW
from test_patterns_database import db as database_fixture, pytestmark as database_marks, data, publish, records, sql

db = database_fixture
pytestmark = database_marks


async def test_s1_shadow_exception_cannot_fail_m1_or_hold_new_safety(db, monkeypatch):
    await publish(db,[*DATA["sightings"],*records(3)])
    async def fail(*args):
        raise RuntimeError("secret shadow diagnostic")
    monkeypatch.setattr(engine,"compute",fail)
    updated={**DATA,"now":(NOW+timedelta(hours=1)).isoformat(),"alerts":[]}
    await ingest_fixture(db,updated)
    await db.wait_for_patterns()
    product=await db.opportunities(NOW+timedelta(hours=1))
    assert product.assessment_state=="complete"
    assert product.items and product.items[0].safety_state!="unknown"
    assert not await sql(db,"SELECT id FROM assessment_runs WHERE status='failed'")
    assert (await sql(db,"SELECT status,error_code FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=product.assessment_id))[0]=={"status":"failed","error_code":"shadow_failed"}
    assert not db.failed
    assert (await read(db,NOW+timedelta(hours=1))).analysis_state=="unassessed"


async def test_s1_blocked_computation_releases_m1_lock_and_response(db,monkeypatch):
    entered,release=asyncio.Event(),asyncio.Event()
    original=engine.compute
    async def slow(c,*args):
        # This connection belongs to the one-slot shadow pool for the entire pause.
        entered.set()
        await release.wait()
        return await original(c,*args)
    monkeypatch.setattr(engine,"compute",slow)
    db.patterns_mode="shadow"
    db.timeout=3
    await ingest_fixture(db,{**DATA,"sightings":[*DATA["sightings"],*records(3)]})
    await asyncio.wait_for(entered.wait(),2)
    base=(await db.opportunities(NOW)).assessment_id
    assert db.pattern_engine.pool.checkedout()==1
    db.patterns_mode="off"
    try:
        newer=await asyncio.wait_for(db.generate({**DATA,"now":(NOW+timedelta(hours=1)).isoformat()}),2)
        assert newer["status"]=="published" and newer["assessment_id"]!=base
        assert (await db.opportunities(NOW+timedelta(hours=1))).assessment_state=="complete"
    finally:
        release.set()
        await db.wait_for_patterns()
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",aid=base))[0]["status"]=="superseded"
    assert not await sql(db,"SELECT id FROM pattern_episodes")


async def test_s1_real_shadow_timeout_does_not_poison_production_pool(db,monkeypatch):
    async def timeout(c,*args):
        await c.execute(text("SELECT pg_sleep(5)"))
    monkeypatch.setattr(engine,"compute",timeout)
    db.patterns_mode="shadow"
    db.pattern_timeout=0.15
    db.timeout=3
    await collect_fixture(db,DATA)
    result=await db.generate(DATA)
    assert result["status"]=="published"
    await db.wait_for_patterns()
    assert not db.failed
    assert db.pattern_engine.pool.checkedout()==0
    assert db.engine.pool.checkedout()==0
    assert (await db.opportunities(NOW)).assessment_state=="complete"
    assert not await sql(db,"SELECT id FROM assessment_runs WHERE status='failed'")
    assert (await sql(db,"SELECT status FROM pattern_generation_runs"))[0]["status"]=="failed"
    await db.ready()


async def test_s1_stale_staged_artifacts_cannot_mutate_episode_registry(db,monkeypatch):
    await publish(db,records(3))
    before=await sql(db,"SELECT * FROM pattern_episodes")
    revisions=await sql(db,"SELECT * FROM pattern_episode_revisions")
    staged,release=asyncio.Event(),asyncio.Event()
    original=engine.stage
    async def pause(*args):
        await original(*args)
        staged.set()
        await release.wait()
    monkeypatch.setattr(engine,"stage",pause)
    old=await db.generate(data(1))
    await asyncio.wait_for(staged.wait(),2)
    db.patterns_mode="off"
    try:
        current=await asyncio.wait_for(db.generate(data(2)),2)
    finally:
        release.set()
        await db.wait_for_patterns()
    assert current["status"]=="published"
    assert await sql(db,"SELECT * FROM pattern_episodes")==before
    assert await sql(db,"SELECT * FROM pattern_episode_revisions")==revisions
    assert (await sql(db,"SELECT status FROM pattern_generation_runs WHERE assessment_run_id=:aid",
                      aid=old["assessment_id"]))[0]["status"]=="superseded"
    assert not await sql(db,"SELECT * FROM pattern_episode_snapshots WHERE assessment_run_id=:aid",aid=old["assessment_id"])
    assert all(r["pattern_episode_id"] is None for r in await sql(db,
        "SELECT pattern_episode_id FROM observation_clusters WHERE assessment_run_id=:aid",aid=old["assessment_id"]))


async def test_s1_m1_fingerprint_independent_of_shadow_policy_engine(db,monkeypatch):
    db.patterns_mode="off"
    first=await db.generate(DATA)
    digest=(await sql(db,"SELECT input_fingerprint FROM assessment_runs WHERE id=:aid",
                      aid=first["assessment_id"]))[0]["input_fingerprint"]
    db.patterns_mode="shadow"
    monkeypatch.setattr(engine,"engine_hash",lambda:"f"*64)
    db.pattern_policies=()
    replay=await db.generate(DATA)
    assert replay["status"]=="superseded" and replay["error"] is None
    assert (await sql(db,"SELECT input_fingerprint FROM assessment_runs WHERE id=:aid",
                      aid=replay["assessment_id"]))[0]["input_fingerprint"]==digest
    assert not await sql(db,"SELECT * FROM pattern_generation_runs")


async def test_s1_shutdown_cancels_shadow_without_changing_m1(db,monkeypatch):
    entered=asyncio.Event()
    async def block(*args):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(engine,"compute",block)
    db.patterns_mode="shadow"
    generated=await db.generate(DATA)
    await asyncio.wait_for(entered.wait(),2)
    await db.close()
    assert not db._pattern_tasks
    rows=await sql(db,"SELECT status FROM assessment_runs WHERE id=:aid",aid=generated["assessment_id"])
    assert rows[0]["status"]=="published"
    assert (await sql(db,"SELECT status,error_code FROM pattern_generation_runs"))[0]=={
        "status":"failed","error_code":"shadow_cancelled"}


def reference_dbscan(points,eps,minimum):
    # Independent Euclidean neighborhood/core-component oracle, not production code.
    neighbors=[{j for j,b in enumerate(points) if math.dist(a,b)<=eps} for a in points]
    core={i for i,n in enumerate(neighbors) if len(n)>=minimum}
    groups=[]
    while core:
        component={min(core)}
        todo=list(component)
        while todo:
            i=todo.pop()
            added=(neighbors[i]&core)-component
            component.update(added)
            todo.extend(added)
        core-=component
        groups.append(component)
    # The randomized generator separates groups enough to avoid shared-border
    # ambiguity; the retained dedicated ambiguous-border shuffle test covers that.
    return {frozenset(set().union(*(neighbors[i] for i in group))) for group in groups}


async def test_s1_preserves_150_randomized_dbscan_point_sets(db):
    rng=random.Random(20261005)
    async with db.engine.connect() as c:
        for trial in range(150):
            coords=[(group*5000+rng.uniform(-350,350),rng.uniform(-350,350))
                    for group in range(rng.randint(1,5)) for _ in range(rng.randint(1,9))]
            coords+=[(rng.uniform(-1000,21000),3000+rng.uniform(0,2000)) for _ in range(rng.randint(0,3))]
            points=[{"report_key":f"{i:03}","nid":i,"x":x,"y":y} for i,(x,y) in enumerate(coords)]
            # Use the actual production SQL, inverse-transforming synthetic meter
            # coordinates first. Transform round-off is far from eps boundaries.
            params={"points":json.dumps(points),"srid":3310,"eps":600.0,"minimum":4}
            query=clustering.CLUSTER_SQL.format(label=clustering.DENSITY_LABEL).replace(
                "ST_Transform(ST_SetSRID(ST_MakePoint(lon,lat),4326),CAST(:srid AS integer))",
                "ST_Transform(ST_Transform(ST_SetSRID(ST_MakePoint(x,y),3310),4326),CAST(:srid AS integer))").replace(
                "lon float8,lat float8","x float8,y float8")
            found=(await c.execute(text(query),params)).mappings().all()
            actual={frozenset(int(key) for key in row["reports"]) for row in found}
            assert actual==reference_dbscan(coords,600,4),trial
