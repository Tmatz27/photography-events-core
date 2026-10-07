"""H3: bounded working window with exact explicit identity dependencies."""
import json
import random
import time
from datetime import timedelta

from sqlalchemy import text

from pec.ingestion import collect_fixture
from pec.patterns import identity
from pec.patterns.policy import POLICIES
from test_database import NOW
from test_final_corrections import origin_claim
from test_hardening import current_groups
from test_patterns_database import BEAR, EAGLE, data, db as database_fixture, record, records, reset, sql
from test_patterns_database import pytestmark as database_marks

db=database_fixture
pytestmark=database_marks


async def seed_history(db,size):
    """Bulk manufacture retained history, not a production ingestion benchmark."""
    async with db.engine.begin() as c:
        sid=(await c.execute(text("SELECT id FROM sources WHERE key='fixture_observations'"))).scalar_one()
        rid=(await c.execute(text("SELECT max(id) FROM source_runs WHERE source_id=:sid"),{"sid":sid})).scalar_one()
        await c.execute(text("""WITH added AS (
            INSERT INTO raw_observations(source_id,source_run_id,external_id,observed_at,fetched_at,
                raw_payload,parser_version,content_sha256)
            SELECT :sid,:rid,'historical-'||i,:old,:old,
                jsonb_build_object('external_id','historical-'||i,'scientific_name',:subject),
                'fixture-2',repeat('a',64) FROM generate_series(1,CAST(:size AS integer)) i RETURNING id
        ) INSERT INTO normalized_observations(raw_observation_id,subject_type,subject_key,observed_at,
            analysis_geometry,sensitive,precision_class,valid_until,source_run_id,content_sha256)
        SELECT id,'species',:subject,:old,ST_SetSRID(ST_MakePoint(-120.5,35.3),4326),
            FALSE,'withheld',:valid,:rid,repeat('a',64) FROM added"""),
            {"sid":sid,"rid":rid,"size":size,"old":NOW-timedelta(days=60),
             "valid":NOW+timedelta(days=14),"subject":BEAR.subject})
        # Deliberately change full provider content provenance: irrelevant history
        # must not change the current logical analytical fingerprint.
        await c.execute(text("UPDATE source_runs SET content_sha256=repeat('b',64) WHERE id=:rid"),{"rid":rid})


async def generate(db,hour=0):
    db.patterns_mode="shadow"
    assert db.timeout==3
    start=time.perf_counter()
    result=await db.generate(data(hour))
    await db.wait_for_patterns()
    elapsed=time.perf_counter()-start
    run=(await sql(db,"SELECT * FROM pattern_generation_runs WHERE assessment_run_id=:aid",aid=result["assessment_id"]))[0]
    assert run["status"]=="published",run
    return result,run,elapsed


async def working(db):
    return await db.pattern_transaction(lambda c: identity.working_set(c,NOW,POLICIES),repeatable=True)


async def test_h3_1_10000_old_rows_four_fresh_publish_default_budget(db,record_property):
    await collect_fixture(db,data(sightings=records(4)))
    await seed_history(db,10000)
    result,run,elapsed=await generate(db)
    record_property("retained_old_assertions",10000)
    record_property("shadow_completion_seconds",elapsed)
    assert run["input_fingerprint"]
    assert (await sql(db,"SELECT independent_report_count FROM observation_clusters WHERE assessment_run_id=:aid",
                      aid=result["assessment_id"]))[0]["independent_report_count"]==4
    assert (await sql(db,"SELECT count(*) AS count FROM normalized_observations WHERE superseded_at IS NULL"))[0]["count"]==10004


async def test_h3_2_outside_window_canonical_target_still_verifies_active_mirror(db):
    old=NOW-timedelta(days=4,minutes=15)
    mirror=origin_claim(observed_at=(NOW-timedelta(days=4)+timedelta(minutes=15)).isoformat())
    await collect_fixture(db,data(sightings=[record(0,observed_at=old.isoformat()),mirror]))
    found=await working(db)
    assert len(found)==2 and min(r["observed_at"] for r in found)==old
    await db.pattern_transaction(lambda c: identity.reconcile(c,NOW,POLICIES),write=True,repeatable=True)
    links=await current_groups(db)
    assert len({r["report_group_id"] for r in links})==1
    assert next(r for r in links if r["provider"]=="fixture_mirror_a")["origin_identity_status"]=="explicit_verified"


async def test_h3_3_corrected_active_canonical_recovers_outside_window_claimant(db):
    old=NOW-timedelta(days=4,minutes=15)
    await collect_fixture(db,data(-97,[record(0,subject=EAGLE.subject,observed_at=old.isoformat()),
                                      origin_claim(observed_at=old.isoformat())]))
    await db.pattern_transaction(lambda c: identity.reconcile(c,NOW-timedelta(hours=97),POLICIES),
                                 write=True,repeatable=True)
    before=await current_groups(db)
    assert len({r["report_group_id"] for r in before})==2
    mirror=next(r for r in before if r["provider"]=="fixture_mirror_a")
    await collect_fixture(db,data(sightings=[record(0,observed_at=(old+timedelta(minutes=30)).isoformat())]))
    found=await working(db)
    assert len(found)==2 and any(r["id"]==mirror["id"] for r in found)
    await db.pattern_transaction(lambda c: identity.reconcile(c,NOW,POLICIES),write=True,repeatable=True)
    assert len({r["report_group_id"] for r in await current_groups(db)})==1
    assert (await sql(db,"SELECT superseded_at FROM observation_report_group_members WHERE id=:id",
                      id=mirror["mid"]))[0]["superseded_at"] is not None


async def test_h3_4_irrelevant_history_excluded_fingerprint_and_members_unchanged(db):
    await collect_fixture(db,data(sightings=records(4)))
    first,first_run,_=await generate(db)
    original_members=await sql(db,"SELECT normalized_observation_id,report_group_id,membership_id FROM cluster_members ORDER BY normalized_observation_id")
    await seed_history(db,10000)
    found=await working(db)
    assert len(found)==4 and all(not r["external_id"].startswith("historical-") for r in found)
    second,second_run,_=await generate(db,1)
    assert first_run["input_fingerprint"]==second_run["input_fingerprint"]
    assert original_members==await sql(db,"""SELECT m.normalized_observation_id,m.report_group_id,m.membership_id
        FROM cluster_members m JOIN observation_clusters c ON c.id=m.cluster_id
        WHERE c.assessment_run_id=:aid ORDER BY m.normalized_observation_id""",aid=second["assessment_id"])
    assert not await sql(db,"""SELECT n.id FROM normalized_observations n JOIN raw_observations r
        ON r.id=n.raw_observation_id JOIN observation_report_group_members m ON m.normalized_observation_id=n.id
        WHERE r.external_id LIKE 'historical-%'""")
    assert first["status"]==second["status"]=="published"


async def test_h3_5_shuffled_insertion_yields_same_identity_fingerprint_clusters(db):
    values=[record(0),origin_claim(),*records(3)[1:]]
    signatures=[]
    for seed in range(4):
        await reset(db)
        shuffled=list(values)
        random.Random(seed).shuffle(shuffled)
        await collect_fixture(db,data(sightings=shuffled))
        result,run,_=await generate(db)
        groups=await sql(db,"""SELECT s.key,r.external_id,g.origin_namespace,g.origin_external_id
            FROM observation_report_group_members m JOIN normalized_observations n ON n.id=m.normalized_observation_id
            JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
            JOIN observation_report_groups g ON g.id=m.report_group_id WHERE m.superseded_at IS NULL
            ORDER BY s.key,r.external_id""")
        clusters=await sql(db,"SELECT cluster_key,independent_report_count FROM observation_clusters WHERE assessment_run_id=:aid",
                           aid=result["assessment_id"])
        signatures.append(json.dumps([run["input_fingerprint"],groups,clusters],sort_keys=True))
    assert len(set(signatures))==1


async def test_h3_6_correction_outside_window_drops_support_keeps_provenance(db):
    await collect_fixture(db,data(sightings=records(4)))
    first,_,_=await generate(db)
    historical=await sql(db,"SELECT * FROM cluster_members ORDER BY cluster_id,normalized_observation_id")
    await collect_fixture(db,data(1,[record(0,observed_at=(NOW-timedelta(days=60)).isoformat())]))
    second,_,_=await generate(db,1)
    counts=await sql(db,"SELECT independent_report_count FROM observation_clusters WHERE assessment_run_id=:aid",aid=second["assessment_id"])
    assert counts[0]["independent_report_count"]==3
    assert historical==await sql(db,"""SELECT m.* FROM cluster_members m JOIN observation_clusters c ON c.id=m.cluster_id
        WHERE c.assessment_run_id=:aid ORDER BY m.cluster_id,m.normalized_observation_id""",aid=first["assessment_id"])


async def test_h3_7_old_record_correction_returns_to_relevance(db):
    await collect_fixture(db,data(sightings=[*records(4),record(99,observed_at=(NOW-timedelta(days=60)).isoformat())]))
    _,_,_=await generate(db)
    assert len(await working(db))==4
    await collect_fixture(db,data(1,[record(99)]))
    result,_,_=await generate(db,1)
    assert (await sql(db,"SELECT independent_report_count FROM observation_clusters WHERE assessment_run_id=:aid",
                      aid=result["assessment_id"]))[0]["independent_report_count"]==5


async def test_h3_25000_old_rows_publish_default_budget(db,record_property):
    await collect_fixture(db,data(sightings=records(4)))
    await seed_history(db,25000)
    _,_,elapsed=await generate(db)
    record_property("retained_old_assertions",25000)
    record_property("shadow_completion_seconds",elapsed)
    assert len(await working(db))==4


async def test_h3_mismatch_logs_only_new_status_or_resolution(db,caplog):
    await collect_fixture(db,data(sightings=[record(0),origin_claim(scientific_name=EAGLE.subject)]))
    await generate(db)
    assert sum('"event": "origin_identity_mismatch"' in r.message for r in caplog.records)==1
    caplog.clear()
    await generate(db,1)
    assert not any('"event": "origin_identity_mismatch"' in r.message for r in caplog.records)
    await collect_fixture(db,data(2,[record(0,subject=EAGLE.subject)]))
    await generate(db,2)
    assert sum('"event": "origin_identity_resolved"' in r.message for r in caplog.records)==1


async def test_h3_no_enabled_policies_loads_no_history(db):
    await collect_fixture(db,data(sightings=records(4)))
    async with db.engine.begin() as c:
        assert await identity.reconcile(c,NOW,())==[]
    assert not await sql(db,"SELECT * FROM observation_report_group_members")
