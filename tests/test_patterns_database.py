"""Real PostGIS acceptance scenarios A1-A38. No mocked clustering or episode storage."""
import asyncio
import random
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.api import create_app
from pec.config import Settings
from pec.database import Database
from pec.ingestion import ingest_fixture
from pec.patterns.api import read
from pec.patterns.policy import Destination, POLICIES
from test_api import SETTINGS, get
from test_database import DATA, NOW, URL, db as database_fixture

db = database_fixture
pytestmark = [pytest.mark.database, pytest.mark.skipif(not URL, reason="Requires disposable PostGIS database")]
BEAR = POLICIES[1]
MONARCH = POLICIES[0]
EAGLE = POLICIES[2]
WHALE = POLICIES[3]
RARE = POLICIES[5]


def record(index=0, subject=BEAR.subject, **changes):
    return {"external_id":f"report-{index}","scientific_name":subject,"observed_at":NOW.isoformat(),
            "latitude":35.3,"longitude":-120.5+index*0.0001,"coordinate_uncertainty_meters":10,**changes}


def records(size, subject=BEAR.subject, **changes):
    return [record(i,subject,**changes) for i in range(size)]


def data(hour=0, sightings=None):
    return {**DATA,"now":(NOW+timedelta(hours=hour)).isoformat(),
            "sightings":sightings if sightings is not None else []}


async def publish(db, sightings, hour=0, policies=None):
    db.patterns_mode = "shadow"
    db.timeout = 30
    if policies is not None:
        db.pattern_policies = policies
    await ingest_fixture(db,data(hour,sightings))
    return await read(db,NOW+timedelta(hours=hour))


async def sql(db, statement, **params):
    async with db.engine.connect() as c:
        return [dict(r) for r in (await c.execute(text(statement),params)).mappings()]


async def clusters(db):
    return await sql(db,"SELECT * FROM observation_clusters ORDER BY id")


async def reset(db):
    async with db.engine.begin() as c:
        await c.execute(text("TRUNCATE sources,locations,assessment_runs,observation_report_groups RESTART IDENTITY CASCADE"))


async def test_postgis_report_density_primitive(db):
    # Exercise SQL directly in a disposable test transaction so a PostGIS/type
    # regression supplies its diagnostic without weakening API sanitization.
    from pec.ingestion import collect_fixture
    from pec.patterns import clustering
    await collect_fixture(db,data(sightings=records(3)))
    async with db.engine.begin() as c:
        rows,_,_=await clustering.load_inputs(c)
        found,_=await clustering.candidates(c,rows,BEAR,NOW)
        assert len(found)==1 and found[0]["independent_report_count"]==3
        assert 0 < found[0]["radius_meters"] < 100


async def test_a1_scattered_monarchs(db):
    rows = [record(i,MONARCH.subject,latitude=32+(i//10)*1.5,longitude=-124+(i%10)*0.9) for i in range(40)]
    result = await publish(db,rows)
    assert not result.items and not result.clusters and not result.preview_opportunities
    assert len((await db.opportunities(NOW)).items) <= 1


async def test_a2_tight_monarch_concentration(db):
    result = await publish(db,records(12,MONARCH.subject))
    assert len(result.items)==1 and result.items[0].state=="developing"
    assert result.items[0].metrics.independent_report_count==12


async def test_a3_same_record_redelivered(db):
    await publish(db,records(1),policies=(replace(BEAR,min_independent_reports=1,minimum_observations=1),))
    await publish(db,records(1),hour=1)
    assert len(await sql(db,"SELECT id FROM raw_observations"))==1
    assert len(await sql(db,"SELECT id FROM normalized_observations WHERE superseded_at IS NULL"))==1
    assert len(await sql(db,"SELECT id FROM observation_report_group_members WHERE superseded_at IS NULL"))==1


def mirrors():
    return [record(0,provider=p,origin_namespace="fixture_observations",origin_external_id="same-origin")
            for p in ("fixture_observations","fixture_mirror_a","fixture_mirror_b")]


async def test_a4_explicit_cross_provider_mirror(db):
    result = await publish(db,mirrors(),policies=(replace(BEAR,min_independent_reports=1,minimum_observations=1),))
    value = result.items[0].metrics
    assert (value.independent_report_count,value.independent_source_count,value.provider_record_count)==(1,3,3)
    assert len(await sql(db,"SELECT * FROM cluster_members WHERE representative"))==1


async def test_a5_two_real_observers(db):
    result = await publish(db,[record(0),record(1)])
    assert result.items[0].metrics.independent_report_count==2
    assert len(await sql(db,"SELECT id FROM observation_report_groups"))==2


async def test_a6_chain_link(db):
    rows=[record(i,longitude=-120.5+i*0.025) for i in range(7)]
    result=await publish(db,rows)
    assert not result.clusters and not result.items
    assert len(await sql(db,"SELECT * FROM pattern_observation_dispositions WHERE disposition='incoherent'"))==7


async def test_a7_bear_activity(db):
    result=await publish(db,records(4))
    assert len(result.items)==1 and result.items[0].phenomenon_key==BEAR.key


async def test_a8_bear_without_cubs(db):
    result=await publish(db,records(4))
    assert result.items[0].metrics.behaviors==["presence"]
    assert not await sql(db,"SELECT * FROM cluster_behavior_summaries WHERE behavior_code='sow_with_cubs'")


async def test_a9_explicit_sow_cub(db):
    result=await publish(db,records(3,behaviors=["sow_with_cubs","feeding"]))
    assert "sow_with_cubs" in result.items[0].metrics.behaviors
    row=(await sql(db,"SELECT * FROM cluster_behavior_summaries WHERE behavior_code='sow_with_cubs'"))[0]
    assert row["independent_report_count"]==3


async def test_a10_ordinary_bald_eagle(db):
    result=await publish(db,records(1,EAGLE.subject))
    assert not result.items
    result=await publish(db,records(6,EAGLE.subject),hour=1)
    assert not result.items


async def test_a11_bald_eagle_fishing(db):
    result=await publish(db,records(3,EAGLE.subject,behaviors=["fishing"]))
    assert len(result.items)==1 and result.items[0].phenomenon_key==EAGLE.key
    assert "fishing" in result.items[0].metrics.behaviors


async def test_a12_humpback_presence(db):
    result=await publish(db,records(4,WHALE.subject))
    assert [i.phenomenon_key for i in result.items]==[WHALE.key]
    assert result.items[0].metrics.behaviors==["presence"]


async def test_a13_humpback_feeding(db):
    result=await publish(db,records(4,WHALE.subject,behaviors=["lunge_feeding"]))
    assert {i.phenomenon_key for i in result.items}=={"humpback_activity","humpback_feeding"}
    assert all("lunge_feeding" in i.metrics.behaviors for i in result.items)
    assert len(await sql(db,"SELECT * FROM cluster_members"))==8


async def test_a14_episode_continuation(db):
    first=await publish(db,records(3))
    changed=[{**r,"observed_at":(NOW+timedelta(hours=1)).isoformat(),"longitude":r["longitude"]+0.001} for r in records(3)]
    second=await publish(db,changed,hour=1)
    assert first.items[0].episode_key==second.items[0].episode_key


async def test_a15_episode_end_restart(db):
    first=await publish(db,records(3))
    ended=await publish(db,[],hour=49)
    assert ended.items[0].state=="ended"
    rows=[{**r,"observed_at":(NOW+timedelta(hours=50)).isoformat()} for r in records(3)]
    restarted=await publish(db,rows,hour=50)
    assert restarted.items[0].episode_key!=first.items[0].episode_key
    assert len(await sql(db,"SELECT * FROM pattern_episodes WHERE status='ended'"))==1


async def test_a16_sensitive_cluster(db,caplog):
    result=await publish(db,records(3,private_location=True,latitude=35.312345678))
    encoded=result.model_dump_json()
    assert result.items[0].redacted and result.items[0].metrics is None
    assert "35.312345678" not in encoded+caplog.text
    assert all(name not in encoded for name in ("centroid_internal","analysis_geometry","radius_meters","exact_geometry"))
    assert (await clusters(db))[0]["independent_report_count"]==3


async def test_a17_centroid_not_destination(db):
    destination=Destination("approved-test","Approved synthetic viewpoint",35.31,-120.49,5000)
    result=await publish(db,records(3),policies=(replace(BEAR,destinations=(destination,)),))
    item=result.preview_opportunities[0]
    assert item.location.latitude==destination.latitude and item.location.longitude==destination.longitude
    assert not item.eligibility and item.held and item.safety_state=="unknown"


async def test_a18_expiring_evidence(db):
    await publish(db,records(3))
    result=await publish(db,[],hour=97)
    assert not result.clusters and result.items[0].state=="ended"


async def test_a19_provider_removes_behavior(db):
    await publish(db,records(3,EAGLE.subject,behaviors=["fishing"]))
    historical=await sql(db,"SELECT * FROM cluster_behavior_summaries WHERE behavior_code='fishing'")
    result=await publish(db,records(3,EAGLE.subject),hour=1)
    assert not result.clusters
    assert await sql(db,"SELECT * FROM cluster_behavior_summaries WHERE behavior_code='fishing'")==historical
    assert result.items[0].metrics is None and result.items[0].state=="developing"


async def test_a20_rare_bird_bypass(db):
    result=await publish(db,records(1,RARE.subject,credible=True))
    assert result.items[0].phenomenon_key==RARE.key and result.items[0].metrics.independent_report_count==1
    await reset(db)
    assert not (await publish(db,records(1,RARE.subject))).items


async def test_a21_core_restart(db):
    first=await publish(db,records(3))
    other=Database(Settings(URL,SETTINGS.api_token,patterns_mode="shadow"))
    try:
        await other.generate(data(1))
        second=await read(other,NOW+timedelta(hours=1))
        assert second.items[0].episode_key==first.items[0].episode_key
    finally:
        await other.close()


async def test_a22_determinism(db):
    first=await publish(db,records(3))
    second=await publish(db,records(3))
    assert first==second
    assert len(await sql(db,"SELECT * FROM pattern_episode_revisions"))==1
    await db.generate(data(1))
    third=await read(db,NOW+timedelta(hours=1))
    assert third.items[0].episode_key==first.items[0].episode_key
    assert len(await sql(db,"SELECT * FROM pattern_episode_revisions"))==1


async def test_a23_raw_flood(db):
    result=await publish(db,records(500,"Corvus corax"))
    assert not result.items and not result.preview_opportunities
    assert len((await db.opportunities(NOW)).items)<=1
    assert len(await sql(db,"SELECT * FROM raw_observations"))==500


async def test_a24_mirrors_do_not_supply_density(db):
    result=await publish(db,mirrors())
    assert not result.items and not result.clusters
    assert len(await sql(db,"SELECT id FROM observation_report_groups"))==1


async def test_a25_high_uncertainty(db):
    rows=records(4,MONARCH.subject)+[record(99,MONARCH.subject,coordinate_uncertainty_meters=15000,longitude=-120.52)]
    await publish(db,records(4,MONARCH.subject))
    first=(await clusters(db))[0]
    result=await publish(db,rows,hour=1)
    assert result.items[0].metrics.independent_report_count==4
    assert len(await sql(db,"SELECT * FROM pattern_observation_dispositions WHERE disposition='regional'"))==1
    same=await sql(db,"SELECT ST_Equals(a.centroid_internal,b.centroid_internal) AS unchanged FROM observation_clusters a JOIN observation_clusters b ON b.assessment_run_id=:aid WHERE a.id=:id",aid=result.assessment_id,id=first["id"])
    assert same[0]["unchanged"]


async def test_a26_area_observation(db):
    rows=records(4,MONARCH.subject)+[record(99,MONARCH.subject,spatial_precision="area")]
    result=await publish(db,rows)
    assert result.items[0].metrics.independent_report_count==4
    assert len(await sql(db,"SELECT * FROM pattern_observation_dispositions WHERE disposition='regional'"))==1


async def test_a27_clusters_approach_without_implicit_merge(db):
    rows=[record(i,longitude=-120.5+(0 if i<2 else 0.07)) for i in range(4)]
    first=await publish(db,rows)
    assert len(first.items)==2
    joined=[{**r,"longitude":-120.47+i*0.0001} for i,r in enumerate(rows)]
    second=await publish(db,joined,hour=1)
    assert len(second.clusters)==1
    assert len(await sql(db,"SELECT * FROM pattern_episodes WHERE status<>'ended'"))==2
    assert not await sql(db,"SELECT * FROM pattern_episodes WHERE merged_into_episode_id IS NOT NULL")


async def test_a28_episode_split(db):
    first=await publish(db,records(5))
    split=[record(i,longitude=-120.5+(-0.025 if i<2 else 0.025)) for i in range(5)]
    second=await publish(db,split,hour=1)
    assert len(second.clusters)==2 and len(second.items)==2
    assert len(await sql(db,"SELECT * FROM pattern_episodes WHERE parent_episode_id IS NOT NULL"))==1
    parent=[r for r in second.items if r.episode_key==first.items[0].episode_key][0]
    assert parent.metrics.independent_report_count==3


async def test_a29_coordinate_correction(db):
    await publish(db,records(3))
    previous=await sql(db,"SELECT id,ST_AsText(centroid_internal) AS point FROM observation_clusters")
    changed=[record(0,longitude=-121.8),record(1),record(2)]
    result=await publish(db,changed,hour=1)
    assert result.clusters[0].metrics.independent_report_count==2
    assert (await sql(db,"SELECT id,ST_AsText(centroid_internal) AS point FROM observation_clusters WHERE id=:id",id=previous[0]["id"]))[0]==previous[0]


async def test_a30_all_support_expires_without_refetch_renewal(db):
    await publish(db,records(3))
    result=await publish(db,records(3),hour=120)
    assert not result.clusters and result.items[0].state=="ended"


async def test_a31_regional_corroboration_not_density(db):
    result=await publish(db,records(12,MONARCH.subject,coordinate_uncertainty_meters=15000))
    assert not result.clusters and not result.items
    assert len(await sql(db,"SELECT * FROM pattern_observation_dispositions WHERE disposition='regional'"))==12


async def test_a32_count_inflation(db):
    result=await publish(db,[record(i,count=count) for i,count in enumerate((10,50,100))])
    assert result.items[0].metrics.max_single_report_count==100
    assert "Largest single report: 100" in result.items[0].summary
    assert "160" not in result.items[0].summary and "exactly 100" not in result.items[0].summary


async def test_a33_report_group_correction(db):
    policy=replace(BEAR,min_independent_reports=1,minimum_observations=1)
    first=await publish(db,mirrors(),policies=(policy,))
    old=(await clusters(db))[0]
    changed=mirrors()
    changed[2].pop("origin_namespace")
    changed[2].pop("origin_external_id")
    second=await publish(db,changed,hour=1)
    assert first.items[0].metrics.independent_report_count==1
    assert second.items[0].metrics.independent_report_count==2
    links=await sql(db,"SELECT * FROM cluster_members WHERE cluster_id=:cid",cid=old["id"])
    assert len({r["report_group_id"] for r in links})==1
    assert await sql(db,"SELECT * FROM observation_report_group_members WHERE superseded_at IS NOT NULL")


async def test_a34_no_approved_destination(db):
    result=await publish(db,records(6,private_location=True))
    assert result.items and not result.preview_opportunities
    assert result.items[0].location is None
    assert (await clusters(db))[0]["public_location_id"] is None


async def test_a35_input_order_randomization(db):
    expected=None
    rows=records(5)
    for seed in range(8):
        await reset(db)
        shuffled=rows[:]
        random.Random(seed).shuffle(shuffled)
        result=await publish(db,shuffled)
        logical=(result.items[0].episode_key,result.items[0].metrics.model_dump(),
                 [(r["cluster_key"],r["independent_report_count"],r["radius_meters"]) for r in await clusters(db)])
        if expected is None:
            expected=logical
        assert logical==expected


async def test_a36_policy_provenance(db):
    first=await publish(db,records(3),policies=(BEAR,))
    old=(await clusters(db))[0]
    second=await publish(db,records(3),hour=1,policies=(replace(BEAR,version="fixture-2"),))
    current=await clusters(db)
    assert current[0]["policy_hash"]==old["policy_hash"]
    assert current[-1]["policy_hash"]!=old["policy_hash"]
    assert {i.state for i in second.items}=={"developing","ended"}
    assert second.items[-1].episode_key!=first.items[0].episode_key or second.items[0].episode_key!=first.items[0].episode_key


async def test_a37_sensitive_metadata_redaction(db):
    destination=Destination("tiny-site","Tiny protected named region",35.3,-120.5,5000,True)
    result=await publish(db,records(4,count=777,private_location=True,behaviors=["sow_with_cubs"]),
                         policies=(replace(BEAR,destinations=(destination,)),))
    assert result.items[0].metrics is None and result.items[0].location is None
    assert result.clusters[0].metrics is None and not result.preview_opportunities
    assert "Tiny protected" not in result.model_dump_json() and "sow_with_cubs" not in result.model_dump_json()


async def test_a38_nonpattern_opportunity(db):
    await publish(db,DATA["sightings"])
    result=await db.opportunities(NOW)
    assert result.items[0].pattern_episode_id is None
    assert result.items[0].evidence_state=="calendar_presence"


async def test_shadow_does_not_promote_or_drop_m1(db):
    destination=Destination("test-site","Synthetic public site",35.3,-120.5,5000)
    result=await publish(db,[*DATA["sightings"],*records(5)],policies=(replace(BEAR,destinations=(destination,)),))
    assert result.items[0].state=="qualified"
    assert result.preview_opportunities[0].held and not result.preview_opportunities[0].eligibility
    normal=await db.opportunities(NOW)
    assert len(normal.items)==1 and normal.items[0].phenomenon_key=="tule_elk_rut"


async def test_debug_authentication_list_detail_and_no_geometry(db):
    result=await publish(db,records(3))
    app=create_app(SETTINGS,db,lambda:NOW)
    assert (await get(app,"/api/v1/debug/patterns",None)).status_code==401
    listed=await get(app,"/api/v1/debug/patterns")
    detail=await get(app,"/api/v1/debug/patterns/"+result.items[0].episode_key)
    assert listed.status_code==detail.status_code==200
    assert listed.json()["assessment_id"]==detail.json()["assessment_id"]
    assert listed.json()["items"]==detail.json()["items"]
    assert "centroid" not in listed.text and "radius" not in listed.text


async def test_unqualified_ids_across_providers_remain_independent(db):
    rows=[record(0,provider=p) for p in ("fixture_observations","fixture_mirror_a","fixture_mirror_b")]
    result=await publish(db,rows)
    assert result.items[0].metrics.independent_report_count==3


async def test_guarded_failure_rolls_back_episode_mutations(db,monkeypatch):
    await publish(db,records(3))
    old=await sql(db,"SELECT * FROM pattern_episodes")
    from pec.patterns import engine
    async def fail(*args,**kwargs):
        raise KeyError("private diagnostic")
    monkeypatch.setattr(engine,"persist_clusters",fail)
    from pec.database import GenerationFailed
    with pytest.raises(GenerationFailed):
        await db.generate(data(1))
    assert await sql(db,"SELECT * FROM pattern_episodes")==old


async def test_older_concurrent_generation_never_changes_episodes(db):
    await publish(db,records(3))
    await asyncio.gather(db.generate(data(2)),db.generate(data(1)))
    current=await read(db,NOW+timedelta(hours=2))
    assert current.analysis_state=="current"
    assert len(await sql(db,"SELECT * FROM pattern_episodes"))==1


async def test_immediate_privacy_raise_redacts_previous_debug(db):
    await publish(db,records(3))
    from pec.ingestion import collect_fixture
    await collect_fixture(db,data(1,records(3,private_location=True)))
    current=await read(db,NOW+timedelta(hours=1))
    assert current.items[0].redacted and current.clusters[0].metrics is None

async def test_explicit_unambiguous_merge_records_lineage(db):
    policy=replace(BEAR,allow_merge=True)
    rows=[record(i,longitude=-120.5+(0 if i<2 else 0.07)) for i in range(4)]
    first=await publish(db,rows,policies=(policy,))
    joined=[{**r,"longitude":-120.47+i*0.0001} for i,r in enumerate(rows)]
    second=await publish(db,joined,hour=1)
    assert len(first.items)==2 and len(second.clusters)==1
    merged=await sql(db,"SELECT * FROM pattern_episodes WHERE merged_into_episode_id IS NOT NULL")
    assert len(merged)==1 and merged[0]["status"]=="ended"
    assert len([item for item in second.items if item.state!="ended"])==1


async def test_ambiguous_dbscan_border_is_deterministic_across_shuffles(db):
    policy=replace(BEAR,eps_meters=1000,min_independent_reports=4,minimum_observations=4,
                   maximum_cluster_diameter_meters=4000)
    offsets=(-1780,-1740,-1700,-820,0,820,1700,1740,1780)
    rows=[record(i,longitude=-120.5+offset/91000) for i,offset in enumerate(offsets)]
    expected=None
    for seed in range(6):
        await reset(db)
        shuffled=rows[:]
        random.Random(seed).shuffle(shuffled)
        result=await publish(db,shuffled,policies=(policy,))
        assert len(result.clusters)==2
        logical=([(row["cluster_key"],row["independent_report_count"]) for row in await clusters(db)],
                 [view.episode_key for view in result.items])
        if expected is None:
            expected=logical
        assert logical==expected


async def test_multiple_assertions_in_one_documentation_event_count_once(db):
    policy=replace(BEAR,min_independent_reports=1,minimum_observations=1)
    result=await publish(db,records(3,report_external_id="one-checklist",behaviors=["feeding"]),policies=(policy,))
    value=result.items[0].metrics
    assert value.observation_count==3 and value.independent_report_count==1
    assert (await sql(db,"SELECT independent_report_count FROM cluster_behavior_summaries WHERE behavior_code='feeding'"))[0]["independent_report_count"]==1


async def test_old_collection_is_not_current_shadow_coverage(db):
    await publish(db,records(3))
    await db.generate(data(25))
    result=await read(db,NOW+timedelta(hours=25))
    assert result.analysis_state=="outdated"


async def test_changed_policy_or_engine_marks_debug_outdated_before_recompute(db,monkeypatch):
    await publish(db,records(3))
    db.pattern_policies=(replace(BEAR,version="next"),)
    assert (await read(db,NOW)).analysis_state=="outdated"
    db.pattern_policies=POLICIES
    from pec.patterns import engine
    monkeypatch.setattr(engine,"engine_hash",lambda:"0"*64)
    assert (await read(db,NOW)).analysis_state=="outdated"

async def test_m2_future_admission_without_refetch(db):
    rows=records(3,observed_at=(NOW+timedelta(hours=2)).isoformat())
    first=await publish(db,rows)
    assert not first.clusters
    await db.generate(data(1.1))
    second=await read(db,NOW+timedelta(hours=1.1))
    assert second.items[0].metrics.independent_report_count==3
    assert len(await sql(db,"SELECT * FROM raw_observations"))==3


async def test_provider_withdrawal_removes_current_support_and_preserves_history(db):
    first=await publish(db,records(3))
    old=(await clusters(db))[0]
    result=await publish(db,records(3,withdrawn=True),hour=1)
    assert first.items and not result.clusters
    assert not await sql(db,"SELECT id FROM normalized_observations WHERE superseded_at IS NULL")
    assert len(await sql(db,"SELECT * FROM cluster_members WHERE cluster_id=:cid",cid=old["id"]))==3

async def test_count_threshold_uses_maximum_single_report(db):
    policy=replace(BEAR,trigger="COUNT_THRESHOLD",count_requirement=50,qualifying_reports=2)
    rows=[record(0,count=10),record(1,count=40)]
    first=await publish(db,rows,policies=(policy,))
    assert not first.clusters
    second=await publish(db,[record(0,count=10),record(1,count=100)],hour=1)
    assert second.items[0].state=="qualified"
    assert second.items[0].metrics.max_single_report_count==100
