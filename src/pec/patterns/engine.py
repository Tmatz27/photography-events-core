"""Persist shadow outputs inside the M1 atomic generation publication."""
from dataclasses import asdict
from datetime import timedelta
import hashlib
from pathlib import Path

from sqlalchemy import text

from .. import CORE_VERSION
from ..logging import event
from . import clustering, episodes
from .policy import canonical_hash


def policy_hash(policies):
    return canonical_hash([asdict(p) for p in sorted(policies,key=lambda p:p.key)])


def engine_hash():
    digest=hashlib.sha256()
    for name in ("identity.py","clustering.py","episodes.py","engine.py","policy.py","api.py"):
        digest.update(name.encode())
        digest.update(Path(__file__).with_name(name).read_bytes().replace(b"\r\n",b"\n"))
    return digest.hexdigest()


async def public_destination(c, policy, cluster):
    # Only source-controlled approvals create these associations. No nearest-site
    # search or arbitrary provider-supplied destination is permitted.
    for destination in sorted(policy.destinations,key=lambda d:d.key):
        if cluster["contains_sensitive_evidence"] and not destination.sensitive_allowed:
            continue
        applicable = (await c.execute(text("""SELECT ST_DWithin(
            ST_GeomFromEWKT(:center)::geography,
            ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,:radius)"""),
            {"center":cluster["center_wkt"],"lon":destination.longitude,"lat":destination.latitude,
             "radius":destination.viewing_radius_meters})).scalar_one()
        if not applicable:
            continue
        lid = (await c.execute(text("""INSERT INTO locations(key,name,geometry,public_geometry,location_type,sensitivity)
            VALUES(:key,:name,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
            ST_SetSRID(ST_MakePoint(:lon,:lat),4326),'public_viewpoint','public')
            ON CONFLICT(key) DO NOTHING RETURNING id"""),
            {"key":destination.key,"name":destination.name,"lon":destination.longitude,"lat":destination.latitude})).scalar_one_or_none()
        if lid is None:
            # An existing location must match the approved public point.
            lid = (await c.execute(text("""SELECT id FROM locations WHERE key=:key AND sensitivity='public'
                AND public_geometry IS NOT NULL AND ST_Equals(public_geometry,
                ST_SetSRID(ST_MakePoint(:lon,:lat),4326))"""),
                {"key":destination.key,"lon":destination.longitude,"lat":destination.latitude})).scalar_one_or_none()
        if lid is not None:
            await c.execute(text("INSERT INTO phenomenon_locations VALUES(:key,:lid,'primary') ON CONFLICT DO NOTHING"),
                            {"key":policy.key,"lid":lid})
            return lid
    event("public_location_unavailable",code="no_applicable_approved_destination")
    return None


async def persist_cluster(c, aid, policy, item, now):
    params = {**item,"aid":aid,"phenomenon":policy.key,"version":policy.version,"hash":policy.hash,
        "engine":CORE_VERSION,"engine_hash":engine_hash(),"crs":policy.clustering_crs,"now":now,
        "window_start":now-timedelta(seconds=policy.temporal_window_seconds),
        "window_end":now+timedelta(seconds=policy.future_tolerance_seconds)}
    columns = ("provider_record_count","observation_count","independent_report_count","independent_source_count",
               "max_single_report_count","first_observed_at","last_observed_at","contains_sensitive_evidence",
               "qualification_state","public_location_id")
    item["id"] = (await c.execute(text(f"""INSERT INTO observation_clusters(assessment_run_id,phenomenon_key,cluster_key,
        pattern_episode_id,policy_version,policy_hash,engine_version,engine_hash,clustering_crs,calculated_at,
        centroid_internal,bounding_center_internal,radius_meters,window_start,window_end,{','.join(columns)})
        VALUES(:aid,:phenomenon,:cluster_key,:pattern_episode_id,:version,:hash,:engine,:engine_hash,:crs,:now,
        ST_GeomFromEWKT(:centroid_wkt),ST_GeomFromEWKT(:center_wkt),:radius_meters,:window_start,:window_end,
        {','.join(':'+key for key in columns)}) RETURNING id"""),params)).scalar_one()
    await c.execute(text("""INSERT INTO cluster_members(cluster_id,normalized_observation_id,report_group_id,membership_id,representative)
        VALUES(:cid,:nid,:gid,:mid,:representative)"""),
        [{"cid":item["id"],"nid":r["id"],"gid":r["report_group_id"],"mid":r["membership_id"],
          "representative":r["id"] in item["representative_ids"]} for r in item["members"]])
    if item["behaviors"]:
        await c.execute(text("""INSERT INTO cluster_behavior_summaries(cluster_id,behavior_code,observation_count,
            independent_report_count,independent_source_count) VALUES(:cid,:code,:observation_count,
            :independent_report_count,:independent_source_count)"""),
            [{"cid":item["id"],"code":code,**counts} for code,counts in item["behaviors"].items()])
    event("cluster_created",code="shadow_candidate")


async def run(c, aid, now, policies, rows, sources, *, published):
    await c.execute(text("""INSERT INTO pattern_generation_runs VALUES(:aid,:hash,:engine_hash,'shadow',:now,0,0)"""),
                    {"aid":aid,"hash":policy_hash(policies),"engine_hash":engine_hash(),"now":now})
    if sources:
        await c.execute(text("""INSERT INTO pattern_generation_sources
            (assessment_run_id,source_id,source_run_id,content_sha256) VALUES(:aid,:source_id,:source_run_id,:content_sha256)"""),
            [{"aid":aid,**source} for source in sources])
    results = {}
    for policy in sorted(policies,key=lambda p:p.key):
        items, dispositions = await clustering.candidates(c,rows,policy,now)
        for item in items:
            item["public_location_id"] = await public_destination(c,policy,item)
            item["pattern_episode_id"] = None
        results[policy.key] = items
        if dispositions:
            await c.execute(text("""INSERT INTO pattern_observation_dispositions VALUES(:aid,:key,:nid,:disposition)"""),
                [{"aid":aid,"key":policy.key,"nid":nid,"disposition":value} for nid,value in sorted(dispositions.items())])
    outcomes = await episodes.assign(c,results,policies,now) if published else {}
    for policy in policies:
        for item in results[policy.key]:
            await persist_cluster(c,aid,policy,item,now)
    if published:
        await episodes.snapshots(c,aid,outcomes,now)
    count = sum(len(items) for items in results.values())
    await c.execute(text("UPDATE pattern_generation_runs SET expected_clusters=:count,expected_episodes=:episodes WHERE assessment_run_id=:aid"),
                    {"count":count,"episodes":len(outcomes),"aid":aid})
