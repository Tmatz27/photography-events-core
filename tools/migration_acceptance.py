"""R20: seed a real 0001 schema, then verify preservation through 0002."""
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pec.config import Settings
from pec.database import DECISION, Database
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
            await c.execute(text("""INSERT INTO raw_observations(source_id,external_id,observed_at,fetched_at,raw_payload,parser_version)
                VALUES(:sid,'legacy-observation',:now,:now,'{"preserve":"provider data"}','fixture-1')"""), {"sid": sid, "now": now})
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
            assert (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0002"
            assert (await c.execute(text("SELECT occurrence_key FROM opportunities WHERE id=1"))).scalar() == result.items[0].occurrence_key
            assert (await c.execute(text("SELECT raw_payload->>'preserve' FROM raw_observations"))).scalar() == "provider data"
        await db.close()
        print("R20 passed: 0001 identity/provider data preserved, 0002 API reads conservative current generation")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
