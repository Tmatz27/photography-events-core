"""R20: seed a real 0001 schema, then verify preservation through 0002."""
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pec.config import Settings
from pec.database import DECISION, MATERIAL, Database
from pec.phenomena import evaluate


async def main(mode):
    settings = Settings.from_env()
    assert settings.database_url.database.endswith("_test")
    data = next(c["input"] for c in json.loads(Path("tests/fixtures/legacy_tule_elk.json").read_text())["cases"]
                if c["name"] == "elk_recent_presence")
    now = datetime.fromisoformat(data["now"])
    if mode == "seed":
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as c:
            assert (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0001"
            aid = (await c.execute(text("""INSERT INTO assessment_runs(generated_at,data_as_of,valid_until,scope,state)
                VALUES(:now,:now,:valid,'tule_elk_rut','complete') RETURNING id"""),
                {"now": now, "valid": now + timedelta(hours=3)})).scalar_one()
            item = evaluate(data)[0]
            lid = (await c.execute(text("""INSERT INTO locations(key,name,location_type,sensitivity)
                VALUES(:key,:name,'public_viewpoint','public') RETURNING id"""),
                {"key": item.location.key, "name": item.location.name})).scalar_one()
            values = {**item.model_dump(), "location_id": lid, "aid": aid,
                      "product": json.dumps(item.model_dump(mode="json"))}
            await c.execute(text(f"""INSERT INTO opportunities(occurrence_key,phenomenon_key,assessment_run_id,
                {','.join(DECISION)},product) VALUES(:occurrence_key,:phenomenon_key,:aid,
                {','.join(':'+key for key in DECISION)},CAST(:product AS jsonb))"""), values)
            sid = (await c.execute(text("INSERT INTO sources(key,name,source_type) VALUES('fixture_observations','Legacy seed','fixture') RETURNING id"))).scalar_one()
            rid = (await c.execute(text("""INSERT INTO source_runs(source_id,cycle_key,attempt_number,started_at,completed_at,status)
                VALUES(:sid,'legacy',1,:now,:now,'success') RETURNING id"""), {"sid": sid, "now": now})).scalar_one()
            raw = (await c.execute(text("""INSERT INTO raw_observations(source_id,source_run_id,external_id,observed_at,fetched_at,
                raw_payload,parser_version,exact_geometry)
                VALUES(:sid,:rid,'legacy-observation',:now,:now,CAST(:payload AS jsonb),'fixture-1',
                ST_SetSRID(ST_MakePoint(-119.8,35.2),4326)) RETURNING id"""),
                {"sid": sid, "rid": rid, "now": now, "payload": json.dumps({"preserve": "provider data",
                "scientific_name": "Cervus canadensis nannodes", "private_location": True})})).scalar_one()
            nid = (await c.execute(text("""INSERT INTO normalized_observations(raw_observation_id,subject_type,subject_key,
                observed_at,valid_until,sensitive,precision_class) VALUES(:raw,'species','Cervus canadensis nannodes',
                :now,:valid,TRUE,'withheld') RETURNING id"""),
                {"raw": raw, "now": now, "valid": now + timedelta(days=14)})).scalar_one()
            await c.execute(text("INSERT INTO opportunity_observation_evidence VALUES(1,:nid,'SUPPORTING')"), {"nid": nid})
            await c.execute(text("INSERT INTO opportunity_context_evidence VALUES(1,:rid,'NEUTRAL')"), {"rid": rid})
            await c.execute(text(f"""INSERT INTO opportunity_revisions(opportunity_id,recorded_at,{','.join(MATERIAL)})
                VALUES(1,:now,{','.join(':'+key for key in MATERIAL)})"""), {**values, "now": now})
        await engine.dispose()
    elif mode == "seed-shadow":
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as c:
            assert (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0003"
            await c.execute(text("""INSERT INTO pattern_generation_runs
                VALUES(1,:hash,:hash,'shadow',:now,0,0)"""),{"hash":"a"*64,"now":now})
        await engine.dispose()
    elif mode == "seed-final":
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as c:
            assert (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0004"
            await c.execute(text("UPDATE normalized_observations SET behavior='bugling'"))
        await engine.dispose()
    else:
        db = Database(settings)
        await db.ready()
        result = await db.opportunities(now)
        assert len(result.items) == 1 and result.items[0].occurrence_key == "tule_elk_rut-2026-09-15"
        assert result.assessment_id is not None
        # The first implementation did not record enough provenance to claim
        # a complete reconstructed assessment. Preserve it as held context.
        assert result.assessment_state == "incomplete" and result.items[0].held
        async with db.engine.connect() as c:
            assert (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0005"
            run=(await c.execute(text("SELECT * FROM pattern_generation_runs WHERE assessment_run_id=1"))).mappings().one()
            assert run["status"]=="published" and run["policy_hash"]==run["engine_hash"]=="a"*64
            assert run["started_at"]==run["completed_at"]==run["calculated_at"]==now
            assert run["input_fingerprint"] is None and run["error_code"] is None
            assert (await c.execute(text("SELECT occurrence_key FROM opportunities WHERE id=1"))).scalar() == result.items[0].occurrence_key
            assert (await c.execute(text("SELECT raw_payload->>'preserve' FROM raw_observations"))).scalar() == "provider data"
            assert (await c.execute(text("SELECT sensitive AND analysis_geometry IS NOT NULL AND public_geometry IS NULL FROM normalized_observations"))).scalar()
            assert (await c.execute(text("SELECT count(*) FROM legacy_observation_evidence"))).scalar() == 1
            assert (await c.execute(text("SELECT count(*) FROM legacy_context_evidence"))).scalar() == 1
            assert (await c.execute(text("SELECT count(*) FROM opportunity_revisions WHERE provenance_status='legacy_unscoped' AND assessment_run_id IS NULL"))).scalar() == 1
            assert (await c.execute(text("SELECT count(*) FROM opportunity_observation_evidence"))).scalar() == 0
            assert (await c.execute(text("SELECT count(*) FROM observation_report_group_members WHERE superseded_at IS NULL"))).scalar() == 1
            assert (await c.execute(text("SELECT spatial_precision FROM normalized_observations"))).scalar() == "unknown"
            assert set((await c.execute(text("SELECT behavior_code FROM normalized_observation_behaviors"))).scalars()) == {"presence","rut"}
        await db.close()
        print("R20 passed: 0001 identity/provider data preserved, 0002 API reads conservative current generation")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
