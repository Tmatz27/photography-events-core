"""Fixture-only ingestion through raw -> normalized -> application -> product.

No live provider is connected in Milestone 1. Normalizers can emit more than
one typed assertion per record; exact source coordinates never become DTOs.
"""
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from .phenomena import evaluate


async def ingest_fixture(db, data):
    now = datetime.fromisoformat(data["now"])
    # The legacy coordinator filters future sightings before evaluating windows.
    if any(datetime.fromisoformat(s["observed_at"]) > now + timedelta(hours=1) for s in data["sightings"]):
        raise ValueError("Future observations are not admissible")
    cycle = str(uuid.uuid4())  # Operational attempt grouping, never product identity.
    normalized_ids, context_ids, logical_sightings = [], [], []
    async with db.engine.begin() as c:
        for key, role in (("fixture_observations", "CORROBORATION"), ("nws_alerts", "SAFETY")):
            sid = (await c.execute(text("""INSERT INTO sources(key,name,source_type)
                VALUES(:key,:name,'fixture') ON CONFLICT(key) DO UPDATE SET name=EXCLUDED.name RETURNING id"""),
                {"key": key, "name": "Synthetic fixture: " + key})).scalar_one()
            await c.execute(text("INSERT INTO source_roles VALUES(:sid,:role) ON CONFLICT DO NOTHING"), {"sid": sid, "role": role})
            success = key != "nws_alerts" or data.get("alerts") is not None
            records = data["sightings"] if key == "fixture_observations" else []
            rid = (await c.execute(text("""INSERT INTO source_runs(source_id,cycle_key,attempt_number,started_at,
                completed_at,status,records_received,records_accepted,provider_updated_at,error_code)
                VALUES(:sid,:cycle,1,:now,:now,:status,:count,:count,:provider,:error) RETURNING id"""),
                {"sid": sid, "cycle": cycle, "now": now, "status": "success" if success else "failure",
                 "count": len(records), "provider": now if success else None,
                 "error": None if success else "fixture_unavailable"})).scalar_one()
            context_ids.append(rid)
            for s in records:
                observed = datetime.fromisoformat(s["observed_at"])
                raw_id = (await c.execute(text("""INSERT INTO raw_observations(source_id,source_run_id,external_id,
                    observed_at,fetched_at,exact_geometry,raw_payload,parser_version)
                    VALUES(:sid,:rid,:eid,:observed,:now,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),CAST(:payload AS jsonb),'fixture-1')
                    ON CONFLICT(source_id,external_id) DO UPDATE SET fetched_at=EXCLUDED.fetched_at
                    RETURNING id"""), {"sid": sid, "rid": rid, "eid": s.get("external_id"),
                    "observed": observed, "now": now, "lon": s["longitude"], "lat": s["latitude"],
                    "payload": json.dumps(s)})).scalar_one()
                # Sensitive fixture coordinates may be retained for restricted
                # ingestion only. No default three-decimal fuzzing rule exists.
                nid = (await c.execute(text("""INSERT INTO normalized_observations(raw_observation_id,subject_type,
                    subject_key,observed_at,analysis_geometry,public_geometry,reported_count,sensitive,precision_class,valid_until)
                    VALUES(:raw,'species',:subject,:observed,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),NULL,:count,:sensitive,'withheld',:valid)
                    ON CONFLICT(raw_observation_id,subject_type,subject_key) DO UPDATE SET subject_key=EXCLUDED.subject_key RETURNING id"""),
                    {"raw": raw_id, "subject": s["scientific_name"], "observed": observed,
                     "lon": None if s.get("private_location") else s["longitude"],
                     "lat": None if s.get("private_location") else s["latitude"],
                     "count": s.get("count"), "sensitive": s.get("private_location", False),
                     "valid": observed + timedelta(days=14)})).scalar_one()
                # Evaluation reads the stored assertion. Refetching cannot
                # substitute a later fetch time for its original observed_at.
                saved = (await c.execute(text("""SELECT subject_key,observed_at,reported_count,
                    ST_X(analysis_geometry) AS longitude,ST_Y(analysis_geometry) AS latitude
                    FROM normalized_observations WHERE id=:id"""), {"id": nid})).mappings().one()
                if saved["latitude"] is None or saved["longitude"] is None:
                    continue
                logical = {**s, **dict(saved), "scientific_name": saved["subject_key"],
                           "observed_at": saved["observed_at"].isoformat()}
                logical_sightings.append(logical)
                # Only assertions that actually support this decision are linked.
                probe = evaluate({**data, "sightings": [logical]})
                if any(p.evidence_state == "calendar_presence" for p in probe):
                    normalized_ids.append(nid)
    items = evaluate({**data, "sightings": logical_sightings})
    await db.persist(data, items, normalized_ids, context_ids)
    return items

