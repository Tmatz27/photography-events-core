"""Fixture-adapter identity claims are qualified and correctable, never fuzzy."""
import math
import json
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from ..logging import event
from .policy import behavior_codes

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


async def reconcile(c, now):
    """Atomically resolve the current fixture set before shadow input capture.

    Claims survive rejection in raw_payload. Read every current trusted claim,
    including independent/rehomed mirrors, so either side's correction retries
    the same validator. No M1 lock or per-record SQL is used. A concurrent provider
    correction either precedes this MVCC snapshot or aborts this shadow-only
    transaction; clustering never consumes half-reconciled memberships.
    """
    rows=[dict(row) for row in (await c.execute(text("""SELECT n.id,n.subject_key,n.observed_at,
        n.behavior,n.coordinate_uncertainty_meters,n.spatial_precision,n.credible,
        ARRAY(SELECT behavior_code FROM normalized_observation_behaviors b
            WHERE b.normalized_observation_id=n.id ORDER BY behavior_code) AS behaviors,
        r.external_id,r.raw_payload,r.fetched_at,s.key AS source_key,
        m.id AS membership_id,m.report_group_id,m.link_basis,m.created_at,
        g.origin_namespace,g.origin_external_id
        FROM normalized_observations n JOIN raw_observations r ON r.id=n.raw_observation_id
        JOIN sources s ON s.id=r.source_id LEFT JOIN observation_report_group_members m
        ON m.normalized_observation_id=n.id AND m.superseded_at IS NULL
        LEFT JOIN observation_report_groups g ON g.id=m.report_group_id
        WHERE n.superseded_at IS NULL AND n.subject_type='species'
        AND s.key IN ('fixture_observations','fixture_mirror_a','fixture_mirror_b')
        ORDER BY s.key,r.external_id,n.id"""))).mappings()]
    claims=defaultdict(list)
    for row in rows:
        payload={**(row["raw_payload"] or {})}
        payload.setdefault("external_id",row["external_id"] or f"legacy-raw-{row['id']}")
        # Old M1 assertions may predate raw behavior fields.
        payload.setdefault("behavior",row["behavior"])
        if row["raw_payload"] is None:
            # Ordinary old provider bodies may have been pruned already. Keep
            # established normalized metadata and an existing explicit link;
            # never invent an origin claim from species, time or geometry.
            payload.update(coordinate_uncertainty_meters=row["coordinate_uncertainty_meters"],
                           spatial_precision=row["spatial_precision"],credible=row["credible"],
                           behaviors=list(row["behaviors"]))
            if row["link_basis"]=="explicit_origin_id":
                payload.update(origin_namespace=row["origin_namespace"],origin_external_id=row["origin_external_id"])
        row["details"]=metadata(payload,row["source_key"])
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
                event("origin_identity_mismatch",code=reason)
            desired.append(dict(nid=row["id"],namespace=namespace,origin=origin,
                basis=basis,status=status,uncertainty=details["uncertainty"],
                precision=details["precision"],credible=details["credible"],
                stamp=max(now,row["fetched_at"],row["created_at"] or now),
                behaviors=details["behaviors"]))
    # Retire corrected/withdrawn assertions in bulk, even when enrichment lagged
    # over multiple M1 commits. Historical cluster membership triples survive.
    await c.execute(text("""UPDATE observation_report_group_members m
        SET superseded_at=GREATEST(:now,m.created_at,n.superseded_at)
        FROM normalized_observations n WHERE n.id=m.normalized_observation_id
        AND n.superseded_at IS NOT NULL AND m.superseded_at IS NULL"""),{"now":now})
    if not desired:
        return
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
