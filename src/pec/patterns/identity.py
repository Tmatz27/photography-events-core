"""Fixture-adapter identity claims are qualified and correctable, never fuzzy."""
import math

from sqlalchemy import text

from ..logging import event
from .policy import behavior_codes

FIXTURE_PROVIDERS = frozenset(("fixture_observations", "fixture_mirror_a", "fixture_mirror_b"))


def metadata(record, provider):
    # This adapter is local synthetic-fixture plumbing, not a generic trusted
    # field supplied by an arbitrary live provider or public API.
    namespace = record.get("origin_namespace", provider)
    origin = record.get("origin_external_id", record.get("report_external_id", record["external_id"]))
    if namespace not in FIXTURE_PROVIDERS or not isinstance(origin, str) or not origin.strip():
        raise ValueError("Untrusted origin namespace or missing qualified identity")
    if ("origin_namespace" in record) != ("origin_external_id" in record):
        raise ValueError("Origin namespace and identity must be supplied together")
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
    return dict(namespace=namespace, origin=origin,
                basis="explicit_origin_id" if "origin_namespace" in record else "provider_identity",
                uncertainty=uncertainty, precision=precision, credible=credible,
                behaviors=behavior_codes(record), withdrawn=withdrawn)


async def supersede(c, raw_id, now):
    changed = await c.execute(text("""UPDATE observation_report_group_members m SET superseded_at=:now
        FROM normalized_observations n WHERE n.id=m.normalized_observation_id
        AND n.raw_observation_id=:raw AND m.superseded_at IS NULL"""), {"raw": raw_id, "now": now})
    if changed.rowcount:
        event("report_group_membership_superseded", code="provider_correction")


async def attach(c, nid, details, now):
    group = (await c.execute(text("""INSERT INTO observation_report_groups(origin_namespace,origin_external_id,created_at)
        VALUES(:namespace,:origin,:now) ON CONFLICT(origin_namespace,origin_external_id)
        DO UPDATE SET origin_external_id=EXCLUDED.origin_external_id RETURNING id"""),
        {**details, "now": now})).scalar_one()
    await c.execute(text("""INSERT INTO observation_report_group_members(report_group_id,normalized_observation_id,
        link_basis,created_at) VALUES(:gid,:nid,:basis,:now)"""),
        {"gid": group, "nid": nid, "basis": details["basis"], "now": now})
    await c.execute(text("""UPDATE normalized_observations SET coordinate_uncertainty_meters=:uncertainty,
        spatial_precision=:precision,credible=:credible WHERE id=:nid"""), {**details, "nid": nid})
    await c.execute(text("""INSERT INTO normalized_observation_behaviors
        (normalized_observation_id,behavior_code,created_at) VALUES(:nid,:code,:now)"""),
        [{"nid": nid, "code": code, "now": now} for code in details["behaviors"]])
    event("report_group_created", code="identity_resolved")
