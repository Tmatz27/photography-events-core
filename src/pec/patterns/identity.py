"""Fixture-adapter identity claims are qualified and correctable, never fuzzy."""
import math
from datetime import timedelta

from sqlalchemy import text

from ..logging import event
from .policy import behavior_codes

FIXTURE_PROVIDERS = frozenset(("fixture_observations", "fixture_mirror_a", "fixture_mirror_b"))
ORIGIN_TIME_TOLERANCE = timedelta(hours=1)


def metadata(record, provider):
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
    return dict(namespace=namespace, origin=origin,local_namespace=provider,local_origin=local_origin,
                basis="explicit_origin_id" if "origin_namespace" in record else "provider_identity",
                uncertainty=uncertainty, precision=precision, credible=credible,
                behaviors=behavior_codes(record), withdrawn=withdrawn)


async def supersede(c, raw_id, now):
    changed = await c.execute(text("""UPDATE observation_report_group_members m SET superseded_at=:now
        FROM normalized_observations n WHERE n.id=m.normalized_observation_id
        AND n.raw_observation_id=:raw AND m.superseded_at IS NULL"""), {"raw": raw_id, "now": now})
    if changed.rowcount:
        event("report_group_membership_superseded", code="provider_correction")


async def group_id(c, namespace, origin, now):
    return (await c.execute(text("""INSERT INTO observation_report_groups(origin_namespace,origin_external_id,created_at)
        VALUES(:namespace,:origin,:now) ON CONFLICT(origin_namespace,origin_external_id)
        DO UPDATE SET origin_external_id=EXCLUDED.origin_external_id RETURNING id"""),
        {"namespace":namespace,"origin":origin,"now":now})).scalar_one()


def mismatch(assertion, references):
    subjects=[row for row in references if row["subject_key"].casefold()==assertion["subject_key"].casefold()]
    if not subjects:
        return "subject_mismatch"
    if not any(abs(row["observed_at"]-assertion["observed_at"])<=ORIGIN_TIME_TOLERANCE for row in subjects):
        return "time_mismatch"
    return None


async def attach(c, nid, details, now):
    group=await group_id(c,details["namespace"],details["origin"],now)
    assertion=(await c.execute(text("SELECT subject_key,observed_at FROM normalized_observations WHERE id=:nid"),
                              {"nid":nid})).mappings().one()
    members=[dict(row) for row in (await c.execute(text("""SELECT n.id AS nid,n.subject_key,n.observed_at,
        m.id AS membership_id,m.created_at,m.link_basis,s.key AS source_key,r.external_id,r.raw_payload
        FROM observation_report_group_members m JOIN normalized_observations n ON n.id=m.normalized_observation_id
        JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
        WHERE m.report_group_id=:gid AND m.superseded_at IS NULL AND n.superseded_at IS NULL"""),
        {"gid":group})).mappings()]
    canonical=[row for row in members if row["source_key"]==details["namespace"]]
    authority=details["local_namespace"]==details["namespace"]
    status="explicit_verified" if authority and details["basis"]=="explicit_origin_id" else "provider_identity"
    basis=details["basis"]
    if basis=="explicit_origin_id" and not authority:
        reason=mismatch(assertion,canonical or members) if members else None
        status="explicit_verified" if canonical and not reason else "explicit_unverified"
        if reason:
            event("origin_identity_mismatch",code=reason)
            group=await group_id(c,details["local_namespace"],details["local_origin"],now)
            basis,status="provider_identity","origin_identity_mismatch"
    else:
        # A canonical arrival/correction can disprove a mirror that arrived first.
        # Rehome only its current link; immutable historical membership survives.
        references=[*canonical,dict(assertion)]
        for member in members:
            if member["link_basis"]!="explicit_origin_id":
                continue
            reason=mismatch(member,references)
            if reason:
                stamp=max(now,member["created_at"])
                payload=member["raw_payload"] or {}
                independent=await group_id(c,member["source_key"],payload.get("report_external_id") or member["external_id"],stamp)
                await c.execute(text("UPDATE observation_report_group_members SET superseded_at=:stamp WHERE id=:id"),
                                {"stamp":stamp,"id":member["membership_id"]})
                await c.execute(text("""INSERT INTO observation_report_group_members
                    (report_group_id,normalized_observation_id,link_basis,created_at)
                    VALUES(:gid,:nid,'provider_identity',:stamp)"""),
                    {"gid":independent,"nid":member["nid"],"stamp":stamp})
                await c.execute(text("UPDATE normalized_observations SET origin_identity_status='origin_identity_mismatch' WHERE id=:nid"),
                                {"nid":member["nid"]})
                event("origin_identity_mismatch",code=reason)
    await c.execute(text("""INSERT INTO observation_report_group_members(report_group_id,normalized_observation_id,
        link_basis,created_at) VALUES(:gid,:nid,:basis,:now)"""),
        {"gid": group, "nid": nid, "basis": basis, "now": now})
    await c.execute(text("""UPDATE normalized_observations SET coordinate_uncertainty_meters=:uncertainty,
        spatial_precision=:precision,credible=:credible,origin_identity_status=:status WHERE id=:nid"""),
        {**details,"status":status,"nid":nid})
    await c.execute(text("""INSERT INTO normalized_observation_behaviors
        (normalized_observation_id,behavior_code,created_at) VALUES(:nid,:code,:now)"""),
        [{"nid": nid, "code": code, "now": now} for code in details["behaviors"]])
    event("report_group_created", code="identity_resolved")
