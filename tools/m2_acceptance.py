"""Disposable Compose M2 smoke test and measured primary query plans."""
import asyncio
import json
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from pec.config import Settings
from pec.database import Database
from pec.ingestion import ingest_fixture
from pec.patterns import clustering
from pec.patterns.policy import POLICIES


async def main():
    settings=Settings.from_env()
    db=Database(settings)
    db.timeout=30
    db.patterns_mode="shadow"
    base=next(c["input"] for c in json.loads(Path("tests/fixtures/legacy_tule_elk.json").read_text())["cases"]
              if c["name"]=="elk_recent_presence")
    now=datetime.fromisoformat(base["now"])+timedelta(hours=1)
    wildlife=[dict(external_id=f"m2-smoke-{i}",scientific_name="Ursus americanus",
        observed_at=now.isoformat(),latitude=35.3,longitude=-120.5+i*0.0000001,
        coordinate_uncertainty_meters=10) for i in range(1000)]
    data={**base,"now":now.isoformat(),"sightings":[*base["sightings"],*wildlife]}
    try:
        await ingest_fixture(db,data)
        await db.wait_for_patterns()
        async def measure(c):
            start=time.perf_counter()
            rows,sources,identity=await clustering.load_inputs(c)
            load_seconds=time.perf_counter()-start
            policy=POLICIES[1]
            start=time.perf_counter()
            candidates,dispositions=await clustering.candidates(c,rows,policy,now)
            cluster_seconds=time.perf_counter()-start
            assert len(candidates)==1 and candidates[0]["independent_report_count"]==1000
            groups,_=clustering.admit(rows,policy,now)
            points=[dict(report_key=k,nid=r["id"],lon=r["longitude"],lat=r["latitude"])
                    for k,group in sorted(groups.items()) for r in [clustering.representative(group)]]
            params=dict(points=json.dumps(points),srid=3310,eps=policy.eps_meters,minimum=policy.min_independent_reports)
            density_plan=(await c.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "+
                clustering.CLUSTER_SQL.format(label=clustering.DENSITY_LABEL)),params)).scalar_one()
            input_plan=(await c.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "+clustering.INPUT_SQL))).scalar_one()
            return {"synthetic_provider_records":len(wildlife),"density_points":len(points),
                    "load_inputs_seconds":round(load_seconds,6),"dbscan_seconds":round(cluster_seconds,6),
                    "candidate_clusters":len(candidates),"policy":asdict(policy),"input_plan":input_plan,
                    "clustering_plan":density_plan}
        report=await db.transaction(measure)
        Path("/tmp/m2-performance.json").write_text(json.dumps(report,indent=2)+"\n")
        print("M2 smoke passed: 1000 synthetic reports, one immutable shadow cluster; query plans captured.")
    finally:
        await db.close()


if __name__=="__main__":
    asyncio.run(main())
