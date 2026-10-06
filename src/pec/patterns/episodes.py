"""Episode mutations occur only after the short shadow publication verifies its base."""
import math
from datetime import timedelta

from sqlalchemy import text

from ..logging import event
from .policy import canonical_hash

ACTIVE_SQL = """SELECT e.*,c.radius_meters AS previous_radius,
 ST_X(ST_Transform(c.bounding_center_internal,c.clustering_crs)) AS previous_x,
 ST_Y(ST_Transform(c.bounding_center_internal,c.clustering_crs)) AS previous_y,
 COALESCE(p.reports,ARRAY[]::text[]) AS previous_reports
 FROM pattern_episodes e LEFT JOIN LATERAL (
 SELECT c.* FROM observation_clusters c JOIN assessment_runs a ON a.id=c.assessment_run_id
 WHERE c.pattern_episode_id=e.id ORDER BY a.data_as_of DESC,c.id DESC LIMIT 1
 ) c ON TRUE LEFT JOIN LATERAL (
 SELECT array_agg(DISTINCT g.origin_namespace||':'||g.origin_external_id) AS reports
 FROM cluster_members m JOIN observation_report_groups g ON g.id=m.report_group_id
 WHERE m.cluster_id=c.id) p ON TRUE
 WHERE e.status<>'ended' ORDER BY e.started_at,e.episode_key"""


def report_names(cluster):
    return {r["origin_namespace"] + ":" + r["origin_external_id"] for r in cluster["members"]}


def compatible(episode, cluster, policy, now):
    if (episode["phenomenon_key"] != policy.key or episode["subject_key"] != policy.subject
            or episode["policy_hash"] != policy.hash or episode["compatibility_key"] != policy.compatibility_key
            or episode["status"] == "ended" or episode["previous_x"] is None
            or now - episode["last_supported_at"] > timedelta(seconds=policy.continuation_gap_seconds)):
        return False
    if (episode["public_location_id"] is not None and cluster["public_location_id"] is not None
            and episode["public_location_id"] != cluster["public_location_id"]):
        return False
    distance = math.hypot(cluster["x"]-episode["previous_x"], cluster["y"]-episode["previous_y"])
    return distance <= policy.episode_spatial_tolerance + cluster["radius_meters"] + episode["previous_radius"]


def strongest(cluster):
    return (-cluster["independent_report_count"], -cluster["last_observed_at"].timestamp(), cluster["cluster_key"])


def match_rank(episode, cluster):
    overlap = len(set(episode["previous_reports"]) & report_names(cluster))
    distance = math.hypot(cluster["x"]-episode["previous_x"], cluster["y"]-episode["previous_y"])
    return (-overlap, distance, episode["started_at"], episode["created_at"], episode["episode_key"])


async def prepare(c, clusters_by_policy, policies, now, rejected=()):
    existing = [dict(r) for r in (await c.execute(text(ACTIVE_SQL))).mappings()]
    basis = registry_hash(existing)
    next_id = -1
    policy_by_key = {p.key: p for p in policies}
    outcomes = {}
    for episode in existing:
        policy = policy_by_key.get(episode["phenomenon_key"])
        if policy is None or policy.hash != episode["policy_hash"]:
            episode.update(status="ended", ended_at=now)
            outcomes[episode["id"]] = (episode, None, "policy_changed")
        elif now - episode["last_supported_at"] > timedelta(seconds=episode["continuation_gap_seconds"]):
            episode.update(status="ended", ended_at=now)
            outcomes[episode["id"]] = (episode, None, "expired")

    for policy in sorted(policies, key=lambda p: p.key):
        clusters = sorted(clusters_by_policy[policy.key], key=strongest)
        eligible = [e for e in existing if e["phenomenon_key"] == policy.key and e["status"] != "ended"]
        options = {cluster["cluster_key"]: [e for e in eligible if compatible(e,cluster,policy,now)]
                   for cluster in clusters}
        available = {e["id"] for e in eligible}
        for cluster in clusters:
            # Re-reading old observations never renews an episode or starts a
            # replacement zombie while the rolling window still includes them.
            support = min(now, cluster["last_observed_at"])
            if now-support > timedelta(seconds=policy.continuation_gap_seconds):
                cluster["pattern_episode_id"] = None
                continue
            choices = sorted(options[cluster["cluster_key"]], key=lambda e: match_rank(e,cluster))
            free = [e for e in choices if e["id"] in available]
            transition = "continued"
            if free:
                episode = free[0]
                available.remove(episode["id"])
                unambiguous = (len(free)>1 and all(
                    sum(e["id"] in {item["id"] for item in opt} for opt in options.values()) == 1
                    and set(e["previous_reports"]) & report_names(cluster) for e in free))
                if policy.allow_merge and unambiguous:
                    episode = min(free, key=lambda e: (e["started_at"], e["created_at"], e["episode_key"]))
                    for loser in free:
                        available.discard(loser["id"])
                        if loser["id"] != episode["id"]:
                            loser.update(status="ended", ended_at=now, merged_into_episode_id=episode["id"])
                            outcomes[loser["id"]] = (loser,None,"merged")
                elif len(free)>1:
                    transition = "merge_ambiguous"
                episode["last_supported_at"] = max(episode["last_supported_at"],support)
            else:
                parent = choices[0]["id"] if choices else None
                key = policy.key + "-" + canonical_hash([policy.key,now.isoformat(),cluster["cluster_key"]])[:24]
                episode = dict(episode_key=key,phenomenon_key=policy.key,subject_key=policy.subject,
                    compatibility_key=policy.compatibility_key,status=cluster["qualification_state"],
                    started_at=min(now,cluster["first_observed_at"]),last_supported_at=support,
                    ended_at=None,public_location_id=cluster["public_location_id"],
                    contains_sensitive_evidence=cluster["contains_sensitive_evidence"],
                    policy_version=policy.version,policy_hash=policy.hash,
                    continuation_gap_seconds=policy.continuation_gap_seconds,
                    parent_episode_id=parent,merged_into_episode_id=None,created_at=now,updated_at=now)
                episode["id"] = next_id
                next_id -= 1
                transition = "split" if parent else "created"
            episode.update(status=cluster["qualification_state"],public_location_id=cluster["public_location_id"],
                           contains_sensitive_evidence=episode["contains_sensitive_evidence"] or cluster["contains_sensitive_evidence"],
                           policy_version=policy.version,policy_hash=policy.hash,updated_at=now)
            cluster["pattern_episode_id"] = episode["id"]
            cluster["contains_sensitive_evidence"] = episode["contains_sensitive_evidence"]
            outcomes[episode["id"]] = (episode,cluster,transition)

    for episode in existing:
        if episode["id"] not in outcomes:
            episode["status"] = "developing"
            transition = "coherence_rejected" if episode["phenomenon_key"] in rejected else "unsupported"
            outcomes[episode["id"]] = (episode,None,transition)
    previous = {}
    for eid,(episode,cluster,transition) in outcomes.items():
        episode["updated_at"] = now
        if eid > 0:
            previous[eid] = (await c.execute(text("""SELECT material_fingerprint FROM pattern_episode_snapshots s
                JOIN assessment_runs a ON a.id=s.assessment_run_id WHERE pattern_episode_id=:eid
                ORDER BY a.data_as_of DESC,s.assessment_run_id DESC LIMIT 1"""),{"eid":eid})).scalar_one_or_none()
    return dict(outcomes=outcomes,registry_hash=basis,previous=previous)


REGISTRY_FIELDS = ("id","episode_key","phenomenon_key","subject_key","compatibility_key","status",
    "started_at","last_supported_at","ended_at","public_location_id","contains_sensitive_evidence",
    "policy_version","policy_hash","continuation_gap_seconds","parent_episode_id","merged_into_episode_id",
    "created_at","updated_at")
REGISTRY_SQL = "SELECT " + ",".join(REGISTRY_FIELDS) + " FROM pattern_episodes WHERE status<>'ended' ORDER BY id"


def registry_hash(rows):
    return canonical_hash([{key:row[key].isoformat() if hasattr(row[key],"isoformat") else row[key]
                           for key in REGISTRY_FIELDS} for row in sorted(rows,key=lambda row:row["id"])])


async def registry_matches(c, plan):
    rows=(await c.execute(text(REGISTRY_SQL))).mappings().all()
    return registry_hash(rows)==plan["registry_hash"]


async def assign(c, plan, now):
    """Apply prepared deterministic mutations; no spatial queries or matching."""
    ids={}
    for eid,(episode,cluster,transition) in plan["outcomes"].items():
        if eid < 0:
            columns=tuple(key for key in episode if key!="id")
            ids[eid]=(await c.execute(text(f"""INSERT INTO pattern_episodes({','.join(columns)})
                VALUES({','.join(':'+key for key in columns)}) RETURNING id"""),episode)).scalar_one()
    outcomes={}
    for eid,(episode,cluster,transition) in plan["outcomes"].items():
        episode["id"]=ids.get(eid,eid)
        for key in ("parent_episode_id","merged_into_episode_id"):
            episode[key]=ids.get(episode[key],episode[key])
        if cluster is not None:
            cluster["pattern_episode_id"]=episode["id"]
        await c.execute(text("""UPDATE pattern_episodes SET status=:status,last_supported_at=:last_supported_at,
            ended_at=:ended_at,public_location_id=:public_location_id,contains_sensitive_evidence=:contains_sensitive_evidence,
            policy_version=:policy_version,policy_hash=:policy_hash,merged_into_episode_id=:merged_into_episode_id,
            updated_at=:updated_at WHERE id=:id"""),episode)
        outcomes[episode["id"]]=(episode,cluster,transition)
        name = ("episode_ended" if episode["status"]=="ended" else
                "episode_split" if transition=="split" else "episode_created" if transition=="created" else "episode_continued")
        event(name,code=transition)
    return outcomes


async def snapshots(c, aid, outcomes, now, previous):
    for episode, cluster, transition in outcomes.values():
        fields = ("status","started_at","last_supported_at","ended_at","public_location_id",
                  "contains_sensitive_evidence","policy_version","policy_hash","parent_episode_id","merged_into_episode_id")
        material = {key: episode[key].isoformat() if hasattr(episode[key],"isoformat") else episode[key] for key in fields}
        material["metrics"] = ({key:cluster[key] for key in ("provider_record_count","observation_count",
            "independent_report_count","independent_source_count","max_single_report_count","behaviors")} if cluster else None)
        material["coherence_rejected"] = transition=="coherence_rejected"
        digest = canonical_hash(material)
        values = {**episode,"aid":aid,"eid":episode["id"],"cid":cluster["id"] if cluster else None,
                  "transition":transition,"fingerprint":digest}
        await c.execute(text(f"""INSERT INTO pattern_episode_snapshots(assessment_run_id,pattern_episode_id,cluster_id,
            {','.join(fields)},transition_code,material_fingerprint)
            VALUES(:aid,:eid,:cid,{','.join(':'+key for key in fields)},:transition,:fingerprint)"""),values)
        if previous.get(episode["id"]) != digest:
            await c.execute(text("""INSERT INTO pattern_episode_revisions(assessment_run_id,pattern_episode_id,recorded_at)
                VALUES(:aid,:eid,:now)"""),{"aid":aid,"eid":episode["id"],"now":now})
