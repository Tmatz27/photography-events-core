"""Record-isolated collection and stored-current admission for the M1 fixture source."""
import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from .logging import event
from .patterns import identity as report_identity

LOCK = 7340191
ROLES = {"fixture_observations": "CORROBORATION", "nws_alerts": "SAFETY"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def safe_payload(record):
    # JSONB cannot store NaN/Infinity. Preserve the remaining diagnostic record
    # while recording invalid numeric values as null; no payload is logged.
    return json.loads(json.dumps(record, default=lambda _: None), parse_constant=lambda _: None)


def validate_record(record):
    observed = datetime.fromisoformat(record["observed_at"])
    if observed.tzinfo is None:
        raise ValueError("aware timestamp required")
    subject = record["scientific_name"]
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject required")
    lat, lon = float(record["latitude"]), float(record["longitude"])
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("invalid point")
    count = record.get("count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 2147483647):
        raise ValueError("invalid count")
    behavior = record.get("behavior")
    if behavior is not None and not isinstance(behavior, str):
        raise ValueError("invalid behavior")
    return dict(observed=observed, valid=observed + timedelta(days=14), subject=subject,
                lat=lat, lon=lon, count=count, behavior=behavior)


async def collect_fixture(db, data):
    """One bounded transaction: attempt, raw corrections, supersession and counts."""
    now = datetime.fromisoformat(data["now"])
    if now.tzinfo is None:
        raise ValueError("aware collection timestamp required")
    cycle = str(uuid.uuid4())

    async def collect(c):
        # Serialize collection with generation, in separate committed transactions.
        # This prevents a correction halfway through generation's logical input read.
        await c.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": LOCK})
        runs = {}
        providers = sorted({r.get("provider", "fixture_observations") for r in data.get("sightings", [])
                            if isinstance(r, dict) and r.get("provider", "fixture_observations") in report_identity.FIXTURE_PROVIDERS})
        roles = {**ROLES, **{key: "CORROBORATION" for key in providers}}
        for key, role in roles.items():
            sid = (await c.execute(text("""INSERT INTO sources(key,name,source_type,requires_stable_ids)
                VALUES(:key,:name,'fixture',TRUE) ON CONFLICT(key) DO UPDATE SET name=EXCLUDED.name RETURNING id"""),
                {"key": key, "name": "Synthetic fixture: " + key})).scalar_one()
            await c.execute(text("INSERT INTO source_roles VALUES(:sid,:role) ON CONFLICT DO NOTHING"), {"sid": sid, "role": role})
            success = key != "nws_alerts" or data.get("alerts") is not None
            records = [r for r in data.get("sightings", []) if
                       (r.get("provider", "fixture_observations") if isinstance(r, dict) else "fixture_observations") == key]
            if key == "fixture_observations":
                records += [r for r in data.get("sightings", []) if isinstance(r, dict)
                            and r.get("provider", "fixture_observations") not in report_identity.FIXTURE_PROVIDERS]
            rid = (await c.execute(text("""INSERT INTO source_runs(source_id,cycle_key,attempt_number,started_at,
                completed_at,status,records_received,provider_updated_at,error_code,context_payload)
                VALUES(:sid,:cycle,1,:now,:now,:status,:count,:provider,:error,CAST(:context AS jsonb)) RETURNING id"""),
                {"sid": sid, "cycle": cycle, "now": now, "status": "success" if success else "failure",
                 "count": len(records), "provider": now if success else None,
                 "error": None if success else "fixture_unavailable",
                 "context": canonical(data.get("alerts")) if key == "nws_alerts" else None})).scalar_one()
            accepted = rejected = 0
            for record in records:
                if (not isinstance(record, dict) or not isinstance(record.get("external_id"), str)
                        or not record["external_id"].strip()):
                    rejected += 1
                    event("parser_failure", source=key, code="stable_id_required")
                    continue
                payload = safe_payload(record)
                digest = fingerprint(payload)
                try:
                    if record.get("provider", "fixture_observations") not in report_identity.FIXTURE_PROVIDERS:
                        raise ValueError("Unknown fixture provider")
                    fields = validate_record(record)
                    details = report_identity.metadata(record, key)
                except (KeyError, ValueError, TypeError, OverflowError):
                    fields = dict(observed=None, valid=None, subject=None, lat=None, lon=None, count=None, behavior=None)
                    rejected += 1
                    event("parser_failure", source=key, code="record_rejected")
                else:
                    accepted += 1
                previous = (await c.execute(text("""SELECT * FROM raw_observations
                    WHERE source_id=:sid AND external_id=:eid FOR UPDATE"""),
                    {"sid": sid, "eid": record["external_id"]})).mappings().first()
                if previous and previous["fetched_at"] > now:
                    continue  # A late older attempt cannot roll current provider state back.
                sensitive = bool(record.get("private_location")) or bool(previous and previous["sensitive"])
                changed = (not previous or previous["content_sha256"] != digest
                           or previous["sensitive"] != sensitive or previous["raw_payload"] is None)
                raw_id = (await c.execute(text("""INSERT INTO raw_observations(source_id,source_run_id,external_id,
                    observed_at,fetched_at,exact_geometry,raw_payload,parser_version,content_sha256,sensitive)
                    VALUES(:sid,:rid,:eid,:observed,:now,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
                    CAST(:payload AS jsonb),'fixture-2',:digest,:sensitive)
                    ON CONFLICT(source_id,external_id) DO UPDATE SET source_run_id=EXCLUDED.source_run_id,
                    observed_at=EXCLUDED.observed_at,fetched_at=EXCLUDED.fetched_at,
                    exact_geometry=EXCLUDED.exact_geometry,raw_payload=EXCLUDED.raw_payload,
                    parser_version=EXCLUDED.parser_version,content_sha256=EXCLUDED.content_sha256,sensitive=EXCLUDED.sensitive
                    RETURNING id"""), {**fields, "sid": sid, "rid": rid, "eid": record["external_id"],
                    "now": now, "payload": canonical(payload), "digest": digest, "sensitive": sensitive})).scalar_one()
                if not changed:
                    continue
                await report_identity.supersede(c, raw_id, now)
                await c.execute(text("""UPDATE normalized_observations SET superseded_at=:now
                    WHERE raw_observation_id=:raw AND superseded_at IS NULL"""), {"now": now, "raw": raw_id})
                # Automation can only raise protection, including historical
                # public points. This is policy, not an irreversible DB trigger.
                if sensitive:
                    await c.execute(text("""UPDATE normalized_observations SET sensitive=TRUE,
                        public_geometry=NULL,precision_class='withheld' WHERE raw_observation_id=:raw"""), {"raw": raw_id})
                if fields["subject"] is None or details["withdrawn"]:
                    continue
                nid = (await c.execute(text("""INSERT INTO normalized_observations(raw_observation_id,subject_type,
                    subject_key,observed_at,analysis_geometry,public_geometry,reported_count,sensitive,
                    precision_class,valid_until,behavior,source_run_id,content_sha256)
                    VALUES(:raw,'species',:subject,:observed,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
                    NULL,:count,:sensitive,'withheld',:valid,:behavior,:rid,:digest) RETURNING id"""),
                    {**fields, "raw": raw_id, "sensitive": sensitive, "rid": rid, "digest": digest,
                     "valid": fields["valid"]})).scalar_one()
                await report_identity.attach(c, nid, details, now)
            if key != "nws_alerts":
                current = (await c.execute(text("""SELECT r.external_id,r.content_sha256,r.sensitive
                    FROM raw_observations r WHERE r.source_id=:sid ORDER BY r.external_id"""), {"sid": sid})).mappings()
                content_hash = fingerprint([dict(row) for row in current])
            else:
                content_hash = fingerprint(data.get("alerts"))
            await c.execute(text("""UPDATE source_runs SET records_accepted=:accepted,records_rejected=:rejected,
                content_sha256=:digest WHERE id=:rid"""),
                {"accepted": accepted, "rejected": rejected, "digest": content_hash, "rid": rid})
            runs[key] = rid
        return runs
    return await db.transaction(collect, write=True)


async def stored_inputs(c, data):
    """Current assertions across batches, admitted BEFORE legacy place grouping."""
    now = datetime.fromisoformat(data["now"])
    sources = (await c.execute(text("""SELECT s.id AS source_id,s.key,r.id AS source_run_id,r.status,
        r.context_payload,r.content_sha256 FROM sources s
        LEFT JOIN LATERAL(SELECT * FROM source_runs r WHERE r.source_id=s.id
            ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
        WHERE s.key IN ('fixture_observations','nws_alerts') ORDER BY s.key"""))).mappings().all()
    rows = (await c.execute(text("""SELECT n.id,n.subject_key,n.observed_at,n.reported_count,n.sensitive,
        n.content_sha256,ST_X(n.analysis_geometry) AS longitude,ST_Y(n.analysis_geometry) AS latitude,
        r.external_id,r.raw_payload FROM normalized_observations n
        JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
        WHERE s.key='fixture_observations' AND n.superseded_at IS NULL AND n.subject_type='species'
        AND n.observed_at BETWEEN :first AND :last AND n.valid_until>=:now
        AND n.analysis_geometry IS NOT NULL ORDER BY r.id,n.id"""),
        {"first": now - timedelta(days=14), "last": now + timedelta(hours=1), "now": now})).mappings().all()
    groups = {}
    logical_records = []
    for row in rows:
        payload = row["raw_payload"] or {}
        sighting = dict(scientific_name=row["subject_key"], observed_at=row["observed_at"].isoformat(),
            latitude=row["latitude"], longitude=row["longitude"], count=row["reported_count"],
            private_location=row["sensitive"], normalized_ids=[row["id"]])
        logical_records.append({**sighting, "normalized_ids": [], "external_id": row["external_id"],
                                "content_sha256": row["content_sha256"]})
        key = (row["subject_key"], payload.get("place") or "Synthetic fixture only")
        if key not in groups:
            groups[key] = sighting
        else:
            saved = groups[key]
            saved["normalized_ids"].append(row["id"])
            saved["observed_at"] = max(saved["observed_at"], sighting["observed_at"])
            saved["private_location"] |= sighting["private_location"]
    safety = next((s for s in sources if s["key"] == "nws_alerts"), None)
    logical = {k: data[k] for k in ("now", "home", "horizon_days", "max_drive_hours", "phenomenon") if k in data}
    logical.update(sightings=list(groups.values()),
                   alerts=safety["context_payload"] if safety and safety["status"] == "success" else None)
    # IDs and fetch timestamps are deliberately excluded from semantic identity.
    identity = {**logical, "sightings": logical_records,
                "sources": [{"key": s["key"], "status": s["status"], "hash": s["content_sha256"]} for s in sources]}
    return logical, sources, identity


async def ingest_fixture(db, data):
    await collect_fixture(db, data)
    result = await db.generate(data)
    return result["items"]

