"""Indexed CAP lookup under retained load in disposable real PostGIS, no network."""
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from pec.config import Settings
from pec.database import Database
from pec.sources.contracts import NWS
from pec.sources.storage import register


async def main():
    settings=Settings.from_env()
    assert make_url(settings.database_url).database.endswith('_test')
    db=Database(settings)
    now=datetime.now(UTC)
    try:
        async def seed(c):
            sid=await register(c,NWS)
            rid=(await c.execute(text("""INSERT INTO source_runs(source_id,cycle_key,attempt_number,started_at,completed_at,status)
                VALUES(:sid,'cap-index-benchmark',1,:now,:now,'failure') RETURNING id"""),dict(sid=sid,now=now))).scalar_one()
            await c.execute(text("""INSERT INTO source_reference_barriers
                SELECT :sid,'benchmark-reference-'||i,CAST(:now AS timestamptz),:rid FROM generate_series(1,100000) i"""),
                dict(sid=sid,now=now,rid=rid))
            await c.execute(text('ANALYZE source_reference_barriers'))
            return sid
        sid=await db.pattern_transaction(seed,write=True)
        statement='SELECT provider_updated_at FROM source_reference_barriers WHERE source_id=:sid AND external_id=:eid'
        params=dict(sid=sid,eid='benchmark-reference-50000')
        samples=[]
        for _ in range(10):
            begin=time.perf_counter()
            result=await db.pattern_transaction(lambda c:c.execute(text(statement),params))
            assert result.scalar_one()==now
            samples.append(time.perf_counter()-begin)
        async def explain(c):
            return (await c.execute(text('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) '+statement),params)).scalar_one()
        plan=await db.pattern_transaction(explain)
        node=plan[0]['Plan']
        assert node['Node Type']=='Index Scan' and node['Actual Rows']==1
        assert node['Index Name']=='source_reference_barriers_pkey'
        report=dict(disposable_synthetic_load=True,retained_reference_barriers=100000,
            samples_seconds=samples,median_seconds=statistics.median(samples),plan=plan,
            deadline=settings.pattern_timeout,production_promotion=False)
        Path('/tmp/collector-operations.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:
        await db.close()


if __name__=='__main__':
    asyncio.run(main())
