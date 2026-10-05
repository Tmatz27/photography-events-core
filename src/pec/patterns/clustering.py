"""Deterministic report-level density points; all distance geometry stays internal."""
import json
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from ..logging import event
from .policy import canonical_hash

INPUT_SQL = """SELECT n.id,n.raw_observation_id,n.subject_key,n.observed_at,n.valid_until,
 n.reported_count,n.sensitive,n.coordinate_uncertainty_meters,n.spatial_precision,n.credible,
 n.content_sha256,n.source_run_id,s.id AS source_id,s.key AS source_key,s.enabled,
 r.external_id,m.id AS membership_id,m.report_group_id,g.origin_namespace,g.origin_external_id,
 ST_X(n.analysis_geometry) AS longitude,ST_Y(n.analysis_geometry) AS latitude,
 ARRAY(SELECT behavior_code FROM normalized_observation_behaviors b
       WHERE b.normalized_observation_id=n.id ORDER BY behavior_code) AS behaviors
 FROM normalized_observations n JOIN raw_observations r ON r.id=n.raw_observation_id
 JOIN sources s ON s.id=r.source_id
 JOIN observation_report_group_members m ON m.normalized_observation_id=n.id AND m.superseded_at IS NULL
 JOIN observation_report_groups g ON g.id=m.report_group_id
 WHERE n.superseded_at IS NULL AND n.subject_type='species'
 AND s.key IN ('fixture_observations','fixture_mirror_a','fixture_mirror_b')
 ORDER BY s.key,r.external_id,n.subject_key"""

SOURCE_SQL = """SELECT s.id AS source_id,s.key,r.id AS source_run_id,r.status,r.content_sha256,r.completed_at
 FROM sources s JOIN LATERAL(SELECT * FROM source_runs WHERE source_id=s.id
 ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
 WHERE s.key IN ('fixture_observations','fixture_mirror_a','fixture_mirror_b')
 ORDER BY s.key"""

# The SQL groups one deterministic point per report. Cluster numbers are local
# query artifacts; membership hashes, not cid values, drive stable tie-breaking.
CLUSTER_SQL = """WITH points AS (
 SELECT report_key,nid,ST_Transform(ST_SetSRID(ST_MakePoint(lon,lat),4326),CAST(:srid AS integer)) AS geom
 FROM jsonb_to_recordset(CAST(:points AS jsonb))
 AS p(report_key text,nid bigint,lon float8,lat float8)
), labelled AS (
 SELECT *,{label} AS cid FROM points
), shapes AS (
 SELECT cid,array_agg(report_key ORDER BY report_key) AS reports,
 ST_Collect(geom ORDER BY report_key) AS shape FROM labelled WHERE cid IS NOT NULL GROUP BY cid
), bounds AS (
 SELECT *,ST_MinimumBoundingRadius(shape) AS circle FROM shapes
)
SELECT reports,ST_AsEWKT(ST_Transform(ST_Centroid(shape),4326)) AS centroid_wkt,
 ST_AsEWKT(ST_Transform((circle).center,4326)) AS center_wkt,
 ST_X((circle).center) AS x,ST_Y((circle).center) AS y,
 (circle).radius AS radius_meters FROM bounds ORDER BY reports"""

DENSITY_LABEL = "ST_ClusterDBSCAN(geom,eps=>CAST(:eps AS float8),minpoints=>CAST(:minimum AS integer)) OVER(ORDER BY report_key)"
SINGLE_LABEL = "row_number() OVER(ORDER BY report_key)"


async def load_inputs(c):
    rows = [dict(r) for r in (await c.execute(text(INPUT_SQL))).mappings()]
    sources = [dict(r) for r in (await c.execute(text(SOURCE_SQL))).mappings()]
    identity = []
    for row in rows:
        row["report_key"] = canonical_hash([row["origin_namespace"], row["origin_external_id"]])
        identity.append({k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in row.items()
                         if k not in ("id", "raw_observation_id", "membership_id", "report_group_id",
                                      "source_id", "source_run_id")})
    source_identity = [{k: s[k] for k in ("key", "status", "content_sha256")} for s in sources]
    return rows, sources, {"observations": identity, "sources": source_identity}


def representative(members):
    return min(members, key=lambda r: (
        r["source_key"] != r["origin_namespace"], r["coordinate_uncertainty_meters"],
        -r["observed_at"].timestamp(), r["source_key"], r["external_id"], r["subject_key"]))


def admit(rows, policy, now):
    groups, dispositions = defaultdict(list), {}
    for row in rows:
        if row["subject_key"].casefold() != policy.subject.casefold():
            continue
        stamp = row["observed_at"]
        if (not row["enabled"] or stamp < now - timedelta(seconds=policy.temporal_window_seconds)
                or stamp > now + timedelta(seconds=policy.future_tolerance_seconds) or row["valid_until"] < now):
            dispositions[row["id"]] = "excluded_time"
        elif (row["spatial_precision"] != "point" or row["coordinate_uncertainty_meters"] is None
              or row["coordinate_uncertainty_meters"] > policy.coordinate_uncertainty_limit
              or row["latitude"] is None or row["longitude"] is None):
            dispositions[row["id"]] = "regional" if policy.allow_regional else "excluded_precision"
        elif not (policy.operating_bounds[0] <= row["longitude"] <= policy.operating_bounds[2]
                  and policy.operating_bounds[1] <= row["latitude"] <= policy.operating_bounds[3]):
            dispositions[row["id"]] = "excluded_precision"
        elif policy.trigger == "EXCEPTIONAL_PRESENCE" and not row["credible"]:
            dispositions[row["id"]] = "excluded_credibility"
        else:
            groups[row["report_key"]].append(row)
            dispositions[row["id"]] = "noise"
    return groups, dispositions


def summarize(members, reps):
    behaviors = {}
    for code in sorted({b for row in members for b in row["behaviors"]}):
        relevant = [r for r in members if code in r["behaviors"]]
        behaviors[code] = dict(observation_count=len(relevant),
            independent_report_count=len({r["report_key"] for r in relevant}),
            independent_source_count=len({r["source_key"] for r in relevant}))
    counts = [r["reported_count"] for r in members if r["reported_count"] is not None]
    return dict(provider_record_count=len({r["raw_observation_id"] for r in members}),
        observation_count=len(members), independent_report_count=len(reps),
        independent_source_count=len({r["source_key"] for r in members}),
        max_single_report_count=max(counts) if counts else None,
        first_observed_at=min(r["observed_at"] for r in members),
        last_observed_at=max(r["observed_at"] for r in members),
        contains_sensitive_evidence=any(r["sensitive"] for r in members), behaviors=behaviors)


async def candidates(c, rows, policy, now):
    groups, dispositions = admit(rows, policy, now)
    reps = {key: representative(members) for key, members in groups.items()}
    if not reps:
        return [], dispositions
    points = [dict(report_key=key,nid=row["id"],lon=row["longitude"],lat=row["latitude"])
              for key,row in sorted(reps.items())]
    params = dict(points=json.dumps(points),srid=policy.clustering_crs,eps=policy.eps_meters,
                  minimum=policy.min_independent_reports)
    label = SINGLE_LABEL if policy.trigger == "EXCEPTIONAL_PRESENCE" else DENSITY_LABEL
    shapes = (await c.execute(text(CLUSTER_SQL.format(label=label)), params)).mappings().all()
    output = []
    for shape in shapes:
        members = [r for key in shape["reports"] for r in groups[key]]
        summary = summarize(members, {key: reps[key] for key in shape["reports"]})
        if 2*shape["radius_meters"] > policy.maximum_cluster_diameter_meters:
            for row in members:
                dispositions[row["id"]] = "incoherent"
            event("cluster_rejected_incoherent", code="diameter_exceeded")
            continue
        if (summary["independent_report_count"] < policy.min_independent_reports
                or summary["observation_count"] < policy.minimum_observations):
            continue
        matching = {r["report_key"] for r in members if set(r["behaviors"]) & set(policy.behaviors)}
        if policy.trigger == "BEHAVIOR_REQUIRED" and len(matching) < policy.behavior_min_reports:
            for row in members:
                dispositions[row["id"]] = "behavior_gate"
            continue
        count_ok = policy.count_requirement is None or (summary["max_single_report_count"] or 0) >= policy.count_requirement
        if policy.trigger == "COUNT_THRESHOLD" and not count_ok:
            continue
        qualified = summary["independent_report_count"] >= policy.qualifying_reports and count_ok
        for row in members:
            dispositions[row["id"]] = "cluster_input"
        output.append({**dict(shape), **summary, "cluster_key": canonical_hash(shape["reports"]),
            "qualification_state": "qualified" if qualified else "developing",
            "members": members, "representative_ids": {reps[key]["id"] for key in shape["reports"]}})
    if any(d in ("regional", "excluded_precision") for d in dispositions.values()):
        event("cluster_low_precision_excluded", code="retained_without_density")
    return sorted(output, key=lambda item: item["cluster_key"]), dispositions
