"""Immutable generation publication with deterministic monotonic ordering."""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from . import CORE_VERSION
from .database import (DECISION, MATERIAL, AssessmentConflict, DatabaseUnavailable, GenerationFailed,
                       REQUIRED_SOURCES)
from .ingestion import LOCK, ROLES, fingerprint, stored_inputs
from .logging import event
from .phenomena import definition, evaluate_with_evidence


async def record_failure(db, data):
    async def save(c):
        now = datetime.fromisoformat(data["now"])
        await c.execute(text("""INSERT INTO assessment_runs(generated_at,data_as_of,valid_until,scope,state,
            status,engine_version,error_code) VALUES(:generated,:now,:valid,'tule_elk_rut','incomplete',
            'failed',:engine,'generation_failed')"""),
            {"generated": datetime.now(UTC), "now": now, "valid": now + timedelta(hours=3), "engine": CORE_VERSION})
    try:
        await db.transaction(save, write=True)
    except Exception:
        event("assessment_failure", code="failure_record_unavailable")


async def generate(db, data, *, evaluator=None):
    evaluator = evaluator or evaluate_with_evidence

    async def publish(c):
        # Collection shares this short M1 lock but commits independently. No
        # provider/network access is allowed inside either transaction.
        await c.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": LOCK})
        await c.execute(text("INSERT INTO assessment_current(id) VALUES(1) ON CONFLICT DO NOTHING"))
        pointer = (await c.execute(text("SELECT assessment_run_id FROM assessment_current WHERE id=1 FOR UPDATE"))).scalar_one()
        current = (await c.execute(text("SELECT * FROM assessment_runs WHERE id=:id"), {"id": pointer})).mappings().first() if pointer else None
        logical, sources, identity = await stored_inputs(c, data)
        from .patterns import clustering as pattern_clustering, engine as pattern_engine
        pattern_rows, pattern_sources = [], []
        if db.patterns_mode == "shadow":
            pattern_rows, pattern_sources, pattern_identity = await pattern_clustering.load_inputs(c)
            identity["patterns"] = {"inputs": pattern_identity, "policies": pattern_engine.policy_hash(db.pattern_policies),
                                    "engine_hash": pattern_engine.engine_hash()}
        rules = definition()
        digest = fingerprint({"inputs": identity, "definition_hash": rules["hash"], "engine": CORE_VERSION})
        now = datetime.fromisoformat(data["now"])
        status, error = "published", None
        if current and now < current["data_as_of"]:
            status = "superseded"
        elif current and now == current["data_as_of"]:
            if digest == current["input_fingerprint"]:
                status = "superseded"
            else:
                status, error = "failed", "input_conflict"
        # Even superseded completed generations have their own immutable items.
        items, evidence = evaluator(logical) if not error else ([], {})
        for item in items:
            if item.data_as_of != now:
                raise ValueError("generation timestamp mismatch")
        good_sources = {s["key"] for s in sources if s["status"] == "success"
                        and (s["key"] != "nws_alerts" or s["context_payload"] is not None)}
        state = "complete" if REQUIRED_SOURCES <= good_sources else "incomplete"
        aid = (await c.execute(text("""INSERT INTO assessment_runs(generated_at,data_as_of,valid_until,scope,state,
            status,input_fingerprint,engine_version,definition_hash,error_code,expected_items)
            VALUES(:generated,:now,:valid,'tule_elk_rut',:state,:status,:fingerprint,:engine,:definition,:error,:count)
            RETURNING id"""), {"generated": datetime.now(UTC), "now": now, "valid": now + timedelta(hours=3),
            "state": state, "status": status, "fingerprint": digest, "engine": CORE_VERSION,
            "definition": rules["hash"], "error": error, "count": len(items)})).scalar_one()
        for source in sources:
            await c.execute(text("""INSERT INTO assessment_sources(assessment_run_id,source_id,source_run_id,role,required,consulted)
                VALUES(:aid,:sid,:rid,:role,TRUE,TRUE)"""),
                {"aid": aid, "sid": source["source_id"], "rid": source["source_run_id"], "role": ROLES[source["key"]]})
        for item in items:
            loc = item.location
            lid = (await c.execute(text("""INSERT INTO locations(key,name,geometry,public_geometry,location_type,sensitivity)
                VALUES(:key,:name,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
                ST_SetSRID(ST_MakePoint(:lon,:lat),4326),'public_viewpoint','public')
                ON CONFLICT(key) DO UPDATE SET name=EXCLUDED.name RETURNING id"""),
                {"key": loc.key, "name": loc.name, "lat": loc.latitude, "lon": loc.longitude})).scalar_one()
            await c.execute(text("INSERT INTO phenomenon_locations VALUES(:key,:location,'primary') ON CONFLICT DO NOTHING"),
                            {"key": item.definition_key, "location": lid})
            oid = (await c.execute(text("""INSERT INTO opportunities(occurrence_key,phenomenon_key,location_id)
                VALUES(:key,:phenomenon,:lid) ON CONFLICT(occurrence_key) DO UPDATE
                SET occurrence_key=EXCLUDED.occurrence_key RETURNING id"""),
                {"key": item.occurrence_key, "phenomenon": item.phenomenon_key, "lid": lid})).scalar_one()
            values = {**item.model_dump(), "location_id": lid, "aid": aid, "oid": oid,
                      "product": json.dumps(item.model_dump(mode="json"))}
            await c.execute(text(f"""INSERT INTO assessment_opportunities(assessment_run_id,opportunity_id,{','.join(DECISION)},product,product_sha256)
                VALUES(:aid,:oid,{','.join(':'+key for key in DECISION)},CAST(:product AS jsonb),
                encode(sha256(convert_to(CAST(:product AS jsonb)::text,'UTF8')),'hex'))"""), values)
            for nid in evidence.get(item.occurrence_key, []):
                await c.execute(text("""INSERT INTO opportunity_observation_evidence
                    VALUES(:aid,:oid,:nid,'SUPPORTING')"""), {"aid": aid, "oid": oid, "nid": nid})
            for source in sources:
                if source["source_run_id"] is not None:
                    await c.execute(text("""INSERT INTO opportunity_context_evidence
                        VALUES(:aid,:oid,:rid,'NEUTRAL')"""), {"aid": aid, "oid": oid, "rid": source["source_run_id"]})
            previous = (await c.execute(text("""SELECT * FROM assessment_opportunities
                WHERE assessment_run_id=:previous AND opportunity_id=:oid"""),
                {"previous": pointer, "oid": oid})).mappings().first() if pointer else None
            if status == "published" and (previous is None or any(previous[k] != values[k] for k in MATERIAL)):
                await c.execute(text(f"""INSERT INTO opportunity_revisions(opportunity_id,recorded_at,
                    assessment_run_id,provenance_status,{','.join(MATERIAL)})
                    VALUES(:oid,:recorded,:aid,'generation',{','.join(':'+k for k in MATERIAL)})"""),
                    {**values, "recorded": datetime.now(UTC)})
        if db.patterns_mode == "shadow" and not error:
            await pattern_engine.run(c, aid, now, db.pattern_policies, pattern_rows, pattern_sources,
                                     published=status == "published")
        if status == "published":
            if pointer:
                await c.execute(text("UPDATE assessment_runs SET status='superseded' WHERE id=:id"), {"id": pointer})
            await c.execute(text("UPDATE assessment_current SET assessment_run_id=:aid WHERE id=1"), {"aid": aid})
        return {"assessment_id": aid, "status": status, "error": error,
                "items": [item.model_copy(update={"assessment_id": aid}) for item in items]}

    try:
        result = await db.transaction(publish, write=True)
    except Exception as exc:
        event("assessment_failure", code="generation_failed")
        await record_failure(db, data)
        if isinstance(exc, DatabaseUnavailable):
            raise
        raise GenerationFailed() from None
    if result["error"]:
        event("assessment_conflict", code="equal_watermark_different_input")
        raise AssessmentConflict()
    return result
