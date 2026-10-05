"""Episode registry mutations occur only in the winning M1 publication transaction."""
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


async def assign(c, clusters_by_policy, policies, now):
    existing = [dict(r) for r in (await c.execute(text(ACTIVE_SQL))).mappings()]
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
                            event("episode_merged",code="unambiguous_policy_merge")
                elif len(free)>1:
                    transition = "merge_ambiguous"
                episode["last_supported_at"] = max(episode["last_supported_at"],support)
                event("episode_continued",code=transition)
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
                columns = tuple(episode)
                episode["id"] = (await c.execute(text(f"""INSERT INTO pattern_episodes({','.join(columns)})
                    VALUES({','.join(':'+k for k in columns)}) RETURNING id"""),episode)).scalar_one()
                transition = "split" if parent else "created"
                event("episode_split" if parent else "episode_created",code="qualifying_candidate")
            episode.update(status=cluster["qualification_state"],public_location_id=cluster["public_location_id"],
                           contains_sensitive_evidence=episode["contains_sensitive_evidence"] or cluster["contains_sensitive_evidence"],
                           policy_version=policy.version,policy_hash=policy.hash,updated_at=now)
            cluster["pattern_episode_id"] = episode["id"]
            cluster["contains_sensitive_evidence"] = episode["contains_sensitive_evidence"]
            outcomes[episode["id"]] = (episode,cluster,transition)

    for episode in existing:
        if episode["id"] not in outcomes:
            episode["status"] = "developing"
            outcomes[episode["id"]] = (episode,None,"unsupported")
    for episode, cluster, transition in outcomes.values():
        episode["updated_at"] = now
        await c.execute(text("""UPDATE pattern_episodes SET status=:status,last_supported_at=:last_supported_at,
            ended_at=:ended_at,public_location_id=:public_location_id,contains_sensitive_evidence=:contains_sensitive_evidence,
            policy_version=:policy_version,policy_hash=:policy_hash,merged_into_episode_id=:merged_into_episode_id,
            updated_at=:updated_at WHERE id=:id"""),episode)
        if episode["status"] == "ended":
            event("episode_ended",code=transition)
    return outcomes


async def snapshots(c, aid, outcomes, now):
    for episode, cluster, transition in outcomes.values():
        fields = ("status","started_at","last_supported_at","ended_at","public_location_id",
                  "contains_sensitive_evidence","policy_version","policy_hash","parent_episode_id","merged_into_episode_id")
        material = {key: episode[key].isoformat() if hasattr(episode[key],"isoformat") else episode[key] for key in fields}
        material["metrics"] = ({key:cluster[key] for key in ("provider_record_count","observation_count",
            "independent_report_count","independent_source_count","max_single_report_count","behaviors")} if cluster else None)
        digest = canonical_hash(material)
        previous = (await c.execute(text("""SELECT material_fingerprint FROM pattern_episode_snapshots s
            JOIN assessment_runs a ON a.id=s.assessment_run_id WHERE pattern_episode_id=:eid
            ORDER BY a.data_as_of DESC,s.assessment_run_id DESC LIMIT 1"""),{"eid":episode["id"]})).scalar_one_or_none()
        values = {**episode,"aid":aid,"eid":episode["id"],"cid":cluster["id"] if cluster else None,
                  "transition":transition,"fingerprint":digest}
        await c.execute(text(f"""INSERT INTO pattern_episode_snapshots(assessment_run_id,pattern_episode_id,cluster_id,
            {','.join(fields)},transition_code,material_fingerprint)
            VALUES(:aid,:eid,:cid,{','.join(':'+key for key in fields)},:transition,:fingerprint)"""),values)
        if previous != digest:
            await c.execute(text("""INSERT INTO pattern_episode_revisions(assessment_run_id,pattern_episode_id,recorded_at)
                VALUES(:aid,:eid,:now)"""),{"aid":aid,"eid":episode["id"],"now":now})
