"""Compute shadow artifacts after M1 commit; publish only against its current base."""
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

from sqlalchemy import text

from .. import CORE_VERSION
from ..logging import event
from . import clustering, episodes, identity as report_identity
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


async def persist_clusters(c, aid, policies, results, now):
    entries=[(policy,item) for policy in policies for item in results[policy.key]]
    if not entries:
        return
    # Bulk headers return their identities by logical policy/member key. The
    # driver never needs one INSERT round trip for every candidate cluster.
    columns=("assessment_run_id","phenomenon_key","cluster_key","pattern_episode_id","policy_version","policy_hash",
        "engine_version","engine_hash","clustering_crs","calculated_at","centroid_internal","bounding_center_internal",
        "radius_meters","window_start","window_end","provider_record_count","observation_count","independent_report_count",
        "independent_source_count","max_single_report_count","first_observed_at","last_observed_at",
        "contains_sensitive_evidence","qualification_state","public_location_id")
    declarations=("assessment_run_id bigint,phenomenon_key text,cluster_key text,pattern_episode_id bigint,"
        "policy_version text,policy_hash text,engine_version text,engine_hash text,clustering_crs integer,"
        "calculated_at timestamptz,centroid_internal text,bounding_center_internal text,radius_meters float8,"
        "window_start timestamptz,window_end timestamptz,provider_record_count integer,observation_count integer,"
        "independent_report_count integer,independent_source_count integer,max_single_report_count integer,"
        "first_observed_at timestamptz,last_observed_at timestamptz,contains_sensitive_evidence boolean,"
        "qualification_state text,public_location_id bigint")
    headers=[]
    source_hash=engine_hash()
    for policy,item in entries:
        header={key:item[key] for key in columns if key in item}
        header.update(assessment_run_id=aid,phenomenon_key=policy.key,policy_version=policy.version,
            policy_hash=policy.hash,engine_version=CORE_VERSION,engine_hash=source_hash,
            clustering_crs=policy.clustering_crs,calculated_at=now,centroid_internal=item["centroid_wkt"],
            bounding_center_internal=item["center_wkt"],window_start=now-timedelta(seconds=policy.temporal_window_seconds),
            window_end=now+timedelta(seconds=policy.future_tolerance_seconds))
        headers.append(header)
    selected=[f"ST_GeomFromEWKT(p.{key})" if key in ("centroid_internal","bounding_center_internal") else f"p.{key}"
              for key in columns]
    inserted=(await c.execute(text(f"""INSERT INTO observation_clusters({','.join(columns)})
        SELECT {','.join(selected)} FROM jsonb_to_recordset(CAST(:headers AS jsonb)) AS p({declarations})
        RETURNING id,phenomenon_key,cluster_key"""),
        {"headers":json.dumps(headers,default=lambda value:value.isoformat(),allow_nan=False)})).mappings()
    ids={(row["phenomenon_key"],row["cluster_key"]):row["id"] for row in inserted}
    memberships,behaviors=[],[]
    for policy,item in entries:
        item["id"]=ids[(policy.key,item["cluster_key"])]
        memberships.extend({"cid":item["id"],"nid":row["id"],"gid":row["report_group_id"],
            "mid":row["membership_id"],"representative":row["id"] in item["representative_ids"]}
            for row in item["members"])
        behaviors.extend({"cid":item["id"],"code":code,**counts} for code,counts in item["behaviors"].items())
        event("cluster_created",code="shadow_candidate")
    await c.execute(text("""INSERT INTO cluster_members(cluster_id,normalized_observation_id,report_group_id,membership_id,representative)
        VALUES(:cid,:nid,:gid,:mid,:representative)"""),memberships)
    if behaviors:
        await c.execute(text("""INSERT INTO cluster_behavior_summaries(cluster_id,behavior_code,observation_count,
            independent_report_count,independent_source_count) VALUES(:cid,:code,:observation_count,
            :independent_report_count,:independent_source_count)"""),behaviors)


async def claim(c, aid, now, policies):
    claimed = (await c.execute(text("""INSERT INTO pattern_generation_runs
        (assessment_run_id,policy_hash,engine_hash,mode,calculated_at,expected_clusters,expected_episodes,status,started_at)
        VALUES(:aid,:hash,:engine,'shadow',:now,0,0,'running',:started)
        ON CONFLICT(assessment_run_id) DO NOTHING RETURNING assessment_run_id"""),
        {"aid":aid,"hash":policy_hash(policies),"engine":engine_hash(),"now":now,
         "started":datetime.now(UTC)})).scalar_one_or_none()
    return claimed


async def server_bounds(c, budget):
    for setting,fraction in (("lock_timeout",0.5),("statement_timeout",0.75),("transaction_timeout",0.9)):
        await c.execute(text("SELECT set_config(:setting,:value,TRUE)"),
            {"setting":setting,"value":str(max(1,int(budget*fraction*1000)))+"ms"})


async def prepare(c, aid, now, policies, *, budget=1.0):
    # Assertions and source hashes must come from one MVCC snapshot even when
    # a collector commits a correction between the two input queries.
    # Enrichment briefly writes M2 metadata on shared assertion rows. Bound
    # backend lock lifetime too, so a stalled enrichment cannot strand a later
    # M1 provider correction behind a terminated client connection.
    await server_bounds(c,budget)
    await report_identity.reconcile(c,now)
    rows, sources, identity = await clustering.load_inputs(c,now,policies)
    await c.execute(text("UPDATE pattern_generation_runs SET input_fingerprint=:hash WHERE assessment_run_id=:aid"),
                    {"aid":aid,"hash":canonical_hash(identity)})
    if sources:
        await c.execute(text("""INSERT INTO pattern_generation_sources
            (assessment_run_id,source_id,source_run_id,content_sha256) VALUES(:aid,:source_id,:source_run_id,:content_sha256)"""),
            [{"aid":aid,**source} for source in sources])
    return rows


class Analysis(dict):
    def __init__(self):
        super().__init__()
        self.rejections=[]
        self.rejected_candidates=[]


async def compute(c, rows, policies, now):
    # No M1 lock, row lock, episode mutation or publication writes.
    results, dispositions = Analysis(), []
    for policy in sorted(policies,key=lambda p:p.key):
        items, reasons = await clustering.candidates(c,rows,policy,now,rejections=results.rejections,
                                                     lineage=results.rejected_candidates)
        results[policy.key] = items
        dispositions.extend({"key":policy.key,"nid":nid,"disposition":value}
                            for nid,value in sorted(reasons.items()))
    return results, dispositions


async def stage(c, aid, policies, results, dispositions, now):
    # Bulk artifacts and destination checks also occur outside the M1 lock.
    for policy in policies:
        for item in results[policy.key]:
            item["public_location_id"] = await public_destination(c,policy,item)
            item["pattern_episode_id"] = None
    await persist_clusters(c,aid,policies,results,now)
    if dispositions:
        await c.execute(text("""INSERT INTO pattern_observation_dispositions
            VALUES(:aid,:key,:nid,:disposition)"""),[{"aid":aid,**row} for row in dispositions])
    await c.execute(text("UPDATE pattern_generation_runs SET expected_clusters=:count WHERE assessment_run_id=:aid"),
                    {"aid":aid,"count":sum(map(len,results.values()))})
    if results.rejections:
        columns=tuple(results.rejections[0])
        await c.execute(text(f"""INSERT INTO pattern_coherence_rejections(assessment_run_id,{','.join(columns)})
            VALUES(:aid,{','.join(':'+key for key in columns)})"""),
            [{"aid":aid,**row} for row in results.rejections])


async def finish(c, aid, results, now, plan, *, budget=1.0):
    # Serialize only the short pointer check + episode/snapshot publication.
    # The separate one-second guard bounds both lock waiting and publication;
    # a brief concurrent M1 commit must not drop a valid current shadow result.
    # Client cancellation alone cannot guarantee backend lock release. These
    # server-local bounds precede every pointer/registry lock and are reset at
    # transaction end. PG18's whole-transaction bound also covers many small SQLs.
    await server_bounds(c,budget)
    current = (await c.execute(text("""SELECT assessment_run_id FROM assessment_current
        WHERE id=1 FOR UPDATE"""))).scalar_one_or_none()
    if current != aid or not await episodes.registry_matches(c,plan):
        await c.execute(text("""UPDATE pattern_generation_runs SET status='superseded',completed_at=:done
            WHERE assessment_run_id=:aid"""),{"aid":aid,"done":datetime.now(UTC)})
        return
    outcomes = await episodes.assign(c,plan,now)
    for items in results.values():
        for item in items:
            await c.execute(text("""UPDATE observation_clusters SET pattern_episode_id=:eid,
                contains_sensitive_evidence=:sensitive WHERE id=:id"""),
                {"id":item["id"],"eid":item["pattern_episode_id"],"sensitive":item["contains_sensitive_evidence"]})
    await episodes.snapshots(c,aid,outcomes,now,plan["previous"])
    await c.execute(text("""UPDATE pattern_generation_runs SET status='published',expected_episodes=:count,
        completed_at=:done WHERE assessment_run_id=:aid"""),
        {"aid":aid,"count":len(outcomes),"done":datetime.now(UTC)})


async def run(db, aid, now, policies):
    # A failure is shadow-only; never call M1 record_failure or change its pointer.
    try:
        claimed = await db.pattern_transaction(lambda c: claim(c,aid,now,policies),write=True)
        if claimed is None:
            return
        finish_budget=min(1.0,db.pattern_timeout,db.timeout/3)
        rows = await db.pattern_transaction(lambda c: prepare(c,aid,now,policies,budget=finish_budget),
                                            write=True,repeatable=True,timeout=finish_budget)
        results, dispositions = await db.pattern_transaction(lambda c: compute(c,rows,policies,now))
        await db.pattern_transaction(lambda c: stage(c,aid,policies,results,dispositions,now),write=True)
        plan = await db.pattern_transaction(lambda c: episodes.prepare(c,results,policies,now,
            rejected=results.rejected_candidates))
        # Bound time holding assessment_current independently of expensive work.
        await db.pattern_transaction(lambda c: finish(c,aid,results,now,plan,budget=finish_budget),
                                     write=True,timeout=finish_budget)
    except asyncio.CancelledError:
        await record_failure(db,aid,"shadow_cancelled")
        raise
    except Exception:
        await record_failure(db,aid,"shadow_failed")


async def record_failure(db, aid, code):
    event("pattern_failure",code=code)
    async def failed(c):
        await c.execute(text("""UPDATE pattern_generation_runs SET status='failed',error_code=:code,
            completed_at=:done WHERE assessment_run_id=:aid AND status='running'"""),
            {"aid":aid,"code":code,"done":datetime.now(UTC)})
    try:
        await db.pattern_transaction(failed,write=True,timeout=min(1.0,db.pattern_timeout))
    except Exception:
        event("pattern_failure",code="failure_record_unavailable")
