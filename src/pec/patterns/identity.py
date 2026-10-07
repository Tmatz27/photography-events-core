"""Fixture-adapter identity claims are qualified and correctable, never fuzzy."""
import math
import json
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from ..logging import event
from .policy import POLICIES, behavior_codes

FIXTURE_PROVIDERS = frozenset(("fixture_observations", "fixture_mirror_a", "fixture_mirror_b"))
ORIGIN_TIME_TOLERANCE = timedelta(hours=1)


def metadata(record, provider, *, enrich=True):
    # This adapter is local synthetic-fixture plumbing, not a generic trusted
    # field supplied by an arbitrary live provider or public API.
    namespace = record.get("origin_namespace", provider)
    origin = record.get("origin_external_id", record.get("report_external_id", record["external_id"]))
    local_origin = record.get("report_external_id",record["external_id"])
    if namespace not in FIXTURE_PROVIDERS or not isinstance(origin, str) or not origin.strip():
        raise ValueError("Untrusted origin namespace or missing qualified identity")
    if ("origin_namespace" in record) != ("origin_external_id" in record):
        raise ValueError("Origin namespace and identity must be supplied together")
    if not isinstance(local_origin,str) or not local_origin.strip():
        raise ValueError("Missing local report identity")
    uncertainty = record.get("coordinate_uncertainty_meters")
    if uncertainty is not None and (isinstance(uncertainty, bool) or
            not isinstance(uncertainty, (int, float)) or not math.isfinite(uncertainty) or uncertainty < 0):
        raise ValueError("Invalid coordinate uncertainty")
    precision = record.get("spatial_precision", "point" if uncertainty is not None else "unknown")
    if precision not in ("point", "area", "unknown"):
        raise ValueError("Invalid spatial precision")
    credible = record.get("credible", False)
    withdrawn = record.get("withdrawn", False)
    if type(credible) is not bool or type(withdrawn) is not bool:
        raise ValueError("Credibility/withdrawal flags must be booleans")
    values=record.get("behaviors",[])
    if not isinstance(values,list) or not all(isinstance(value,str) for value in values):
        raise ValueError("Behavior terms must be strings")
    return dict(namespace=namespace, origin=origin,local_namespace=provider,local_origin=local_origin,
                basis="explicit_origin_id" if "origin_namespace" in record else "provider_identity",
                uncertainty=uncertainty, precision=precision, credible=credible,
                behaviors=behavior_codes(record) if enrich else (), withdrawn=withdrawn)


def mismatch(assertion, references):
    subjects=[row for row in references if row["subject_key"].casefold()==assertion["subject_key"].casefold()]
    if not subjects:
        return "subject_mismatch"
    if not any(abs(row["observed_at"]-assertion["observed_at"])<=ORIGIN_TIME_TOLERANCE for row in subjects):
        return "time_mismatch"
    return None



ROW_SELECT = """SELECT n.id,n.subject_key,n.observed_at,n.origin_identity_status,
 n.behavior,n.coordinate_uncertainty_meters,n.spatial_precision,n.credible,
 ARRAY(SELECT behavior_code FROM normalized_observation_behaviors b
       WHERE b.normalized_observation_id=n.id ORDER BY behavior_code) AS behaviors,
 r.id AS raw_observation_id,r.external_id,r.raw_payload,r.fetched_at,s.key AS source_key,
 m.id AS membership_id,m.report_group_id,m.link_basis,m.created_at,
 g.origin_namespace,g.origin_external_id
 FROM normalized_observations n JOIN raw_observations r ON r.id=n.raw_observation_id
 JOIN sources s ON s.id=r.source_id LEFT JOIN observation_report_group_members m
 ON m.normalized_observation_id=n.id AND m.superseded_at IS NULL
 LEFT JOIN observation_report_groups g ON g.id=m.report_group_id
 WHERE n.superseded_at IS NULL AND n.subject_type='species'
 AND s.key IN ('fixture_observations','fixture_mirror_a','fixture_mirror_b')"""
ROW_ORDER = " ORDER BY s.key,r.external_id,n.subject_key,n.id"
ACTIVE_SQL = ROW_SELECT + """
 AND n.observed_at BETWEEN :window_start AND :window_end AND n.valid_until>=:now""" + ROW_ORDER
ROWS_SQL = ROW_SELECT + " AND n.id=ANY(CAST(:ids AS bigint[]))" + ROW_ORDER

# OFFSET 0 preserves the per-qualified-key index lookup rather than flattening
# a tiny key set into a scan of every retained provider body. This is bulk SQL,
# not one network round trip per observation. Both sides of rejected claims are
# found from their durable adapter contract, independent of current membership.
DEPENDENCY_SQL = """WITH keys AS MATERIALIZED (
 SELECT * FROM jsonb_to_recordset(CAST(:keys AS jsonb)) AS k(namespace text,origin text)
)
SELECT q.id FROM keys k JOIN sources s ON s.key=k.namespace
CROSS JOIN LATERAL (
 SELECT n.id FROM raw_observations r JOIN normalized_observations n ON n.raw_observation_id=r.id
 WHERE r.source_id=s.id
 AND COALESCE(r.raw_payload->>'report_external_id',r.external_id,'legacy-raw-'||r.id::text)=k.origin
 AND n.superseded_at IS NULL AND n.subject_type='species'
 OFFSET 0
) q
UNION
SELECT q.id FROM keys k CROSS JOIN LATERAL (
 SELECT n.id FROM raw_observations r JOIN normalized_observations n ON n.raw_observation_id=r.id
 JOIN sources s ON s.id=r.source_id
 WHERE r.raw_payload ? 'origin_namespace' AND r.raw_payload ? 'origin_external_id'
 AND r.raw_payload->>'origin_namespace'=k.namespace AND r.raw_payload->>'origin_external_id'=k.origin
 AND n.superseded_at IS NULL AND n.subject_type='species'
 AND s.key IN ('fixture_observations','fixture_mirror_a','fixture_mirror_b')
 OFFSET 0
) q
UNION
SELECT n.id FROM keys k JOIN observation_report_groups g
ON g.origin_namespace=k.namespace AND g.origin_external_id=k.origin
JOIN observation_report_group_members m ON m.report_group_id=g.id AND m.superseded_at IS NULL
JOIN normalized_observations n ON n.id=m.normalized_observation_id
JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
WHERE n.superseded_at IS NULL AND n.subject_type='species' AND r.raw_payload IS NULL
AND m.link_basis='explicit_origin_id'
AND s.key IN ('fixture_observations','fixture_mirror_a','fixture_mirror_b')"""

RETIRE_SQL = """UPDATE observation_report_group_members m
 SET superseded_at=GREATEST(:now,m.created_at,n.superseded_at)
 FROM normalized_observations n WHERE n.id=m.normalized_observation_id
 AND n.raw_observation_id=ANY(CAST(:raw_ids AS bigint[]))
 AND n.superseded_at IS NOT NULL AND m.superseded_at IS NULL"""


def details_for(row):
    payload={**(row["raw_payload"] or {})}
    payload.setdefault("external_id",row["external_id"] or f"legacy-raw-{row['raw_observation_id']}")
    payload.setdefault("behavior",row["behavior"])
    if row["raw_payload"] is None:
        payload.update(coordinate_uncertainty_meters=row["coordinate_uncertainty_meters"],
            spatial_precision=row["spatial_precision"],credible=row["credible"],behaviors=list(row["behaviors"]))
        if row["link_basis"]=="explicit_origin_id":
            payload.update(origin_namespace=row["origin_namespace"],origin_external_id=row["origin_external_id"])
    return metadata(payload,row["source_key"])


def dependency_keys(rows):
    return {(d["namespace"],d["origin"]) for d in (r["details"] for r in rows)} | {
        (d["local_namespace"],d["local_origin"]) for d in (r["details"] for r in rows)}


async def working_set(c, now, policies):
    """Active policy window plus transitive explicit identity dependencies only."""
    if not policies:
        return []
    from .clustering import input_window
    rows=[dict(r) for r in (await c.execute(text(ACTIVE_SQL),input_window(now,policies))).mappings()]
    found={r["id"]:r for r in rows}
    for row in rows:
        row["details"]=details_for(row)
    visited=set()
    pending=dependency_keys(rows)
    while pending:
        visited.update(pending)
        keys=json.dumps([dict(namespace=ns,origin=origin) for ns,origin in sorted(pending)])
        ids=set((await c.execute(text(DEPENDENCY_SQL),{"keys":keys})).scalars())-found.keys()
        if not ids:
            break
        batch=[dict(r) for r in (await c.execute(text(ROWS_SQL),{"ids":sorted(ids)})).mappings()]
        for row in batch:
            row["details"]=details_for(row)
            found[row["id"]]=row
        pending=dependency_keys(batch)-visited
    return sorted(found.values(),key=lambda r:(r["source_key"],r["external_id"] or "",r["subject_key"],r["id"]))


async def reconcile(c, now, policies=POLICIES):
    """Resolve only this run's active set and explicit dependency closure.

    All reads/writes share capture's MVCC snapshot. Old unrelated assertions are
    neither loaded nor retired. A failed reconciliation rolls back shadow only.
    """
    rows=await working_set(c,now,policies)
    claims=defaultdict(list)
    for row in rows:
        details=row["details"]
        claims[(details["namespace"],details["origin"])].append(row)
    desired=[]
    for target,members in sorted(claims.items()):
        canonical=[r for r in members if r["source_key"]==target[0]]
        # Without a canonical record, deterministic peers validate only the
        # supplied explicit relationship. Never search species/time/geometry.
        references=canonical or members[:1]
        for row in members:
            details=row["details"]
            explicit=details["basis"]=="explicit_origin_id"
            authority=row["source_key"]==target[0]
            reason=mismatch(row,references) if explicit and not authority else None
            namespace,origin=target
            basis=details["basis"]
            status="explicit_verified" if explicit and (authority or canonical) else (
                "explicit_unverified" if explicit else "provider_identity")
            if reason:
                namespace,origin=details["local_namespace"],details["local_origin"]
                basis,status="provider_identity","origin_identity_mismatch"
                if row["origin_identity_status"]!=status:
                    event("origin_identity_mismatch",code=reason)
            elif row["origin_identity_status"]=="origin_identity_mismatch":
                event("origin_identity_resolved",code=status)
            desired.append(dict(nid=row["id"],namespace=namespace,origin=origin,
                basis=basis,status=status,uncertainty=details["uncertainty"],
                precision=details["precision"],credible=details["credible"],
                stamp=max(now,row["fetched_at"],row["created_at"] or now),
                behaviors=details["behaviors"]))
    if not desired:
        return []
    # Only retire superseded history belonging to a selected provider record.
    # Irrelevant old current assertions are never superseded by their age.
    await c.execute(text(RETIRE_SQL),{"now":now,"raw_ids":sorted({r["raw_observation_id"] for r in rows})})
    payload=json.dumps(desired,default=lambda value:value.isoformat(),allow_nan=False)
    declaration="""nid bigint,namespace text,origin text,basis text,status text,
        uncertainty float8,precision text,credible boolean,stamp timestamptz,behaviors jsonb"""
    records=f"jsonb_to_recordset(CAST(:items AS jsonb)) AS p({declaration})"
    params={"items":payload}
    await c.execute(text(f"""INSERT INTO observation_report_groups
        (origin_namespace,origin_external_id,created_at)
        SELECT namespace,origin,min(stamp) FROM {records} GROUP BY namespace,origin
        ON CONFLICT(origin_namespace,origin_external_id) DO NOTHING"""),params)
    await c.execute(text(f"""UPDATE observation_report_group_members m
        SET superseded_at=GREATEST(p.stamp,m.created_at)
        FROM {records},observation_report_groups g
        WHERE m.normalized_observation_id=p.nid AND m.superseded_at IS NULL
        AND g.origin_namespace=p.namespace AND g.origin_external_id=p.origin
        AND (m.report_group_id<>g.id OR m.link_basis<>p.basis)"""),params)
    await c.execute(text(f"""INSERT INTO observation_report_group_members
        (report_group_id,normalized_observation_id,link_basis,created_at)
        SELECT g.id,p.nid,p.basis,p.stamp FROM {records}
        JOIN observation_report_groups g ON g.origin_namespace=p.namespace AND g.origin_external_id=p.origin
        WHERE NOT EXISTS(SELECT 1 FROM observation_report_group_members m
            WHERE m.normalized_observation_id=p.nid AND m.superseded_at IS NULL)"""),params)
    await c.execute(text(f"""UPDATE normalized_observations n
        SET coordinate_uncertainty_meters=p.uncertainty,spatial_precision=p.precision,
            credible=p.credible,origin_identity_status=p.status
        FROM {records} WHERE n.id=p.nid AND
        (n.coordinate_uncertainty_meters,n.spatial_precision,n.credible,n.origin_identity_status)
        IS DISTINCT FROM (p.uncertainty,p.precision,p.credible,p.status)"""),params)
    await c.execute(text(f"""INSERT INTO normalized_observation_behaviors
        (normalized_observation_id,behavior_code,created_at)
        SELECT p.nid,b.code,p.stamp FROM {records}
        CROSS JOIN LATERAL jsonb_array_elements_text(p.behaviors) AS b(code)
        ON CONFLICT(normalized_observation_id,behavior_code) DO NOTHING"""),params)
    by_id={r["id"]:r for r in rows}
    return [dict(provider=by_id[d["nid"]]["source_key"],record=d["origin"],namespace=d["namespace"],
        claimed_namespace=by_id[d["nid"]]["details"]["namespace"],
        claimed_origin=by_id[d["nid"]]["details"]["origin"],
        subject=by_id[d["nid"]]["subject_key"],observed_at=by_id[d["nid"]]["observed_at"].isoformat(),
        status=d["status"]) for d in desired]
