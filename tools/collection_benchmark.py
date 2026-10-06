"""Compare real collection implementations on the same disposable PostGIS DB."""
import asyncio
import importlib.util
import json
import time
from pathlib import Path

from sqlalchemy import event, text

from pec.config import Settings
from pec.database import Database, DatabaseUnavailable
from pec.ingestion import collect_fixture

BASELINES=Path("/tmp/collection-baselines")


def historical(name,filename,package):
    spec=importlib.util.spec_from_file_location(name,BASELINES/filename)
    module=importlib.util.module_from_spec(spec)
    module.__package__=package
    spec.loader.exec_module(module)
    return module


async def main():
    db=Database(Settings.from_env())
    assert db.timeout==3
    old_m1=historical("benchmark_m1","m1-ingestion.py","pec")
    old_m2=historical("benchmark_m2","m2-ingestion.py","pec")
    old_m2.report_identity=historical("benchmark_identity","m2-identity.py","pec.patterns")
    base=next(c["input"] for c in json.loads(Path("tests/fixtures/legacy_tule_elk.json").read_text())["cases"]
              if c["name"]=="elk_recent_presence")
    measurements=[]
    try:
        for size in (100,500,1000):
            for label,collect,mode in (
                ("accepted_m1",old_m1.collect_fixture,"off"),
                ("pre_fix_m2_off",old_m2.collect_fixture,"off"),
                ("corrected_m2_off",collect_fixture,"off"),
                ("corrected_m2_shadow",collect_fixture,"shadow"),
            ):
                for trial in (1,2):
                    async with db.engine.begin() as c:
                        await c.execute(text("TRUNCATE sources,locations,assessment_runs,observation_report_groups RESTART IDENTITY CASCADE"))
                    fixture={**base,"sightings":[dict(external_id=f"benchmark-{i}",
                        scientific_name="Cervus canadensis nannodes",observed_at=base["now"],
                        latitude=35.3,longitude=-120.5,coordinate_uncertainty_meters=10,
                        behavior="bugling") for i in range(size)]}
                    db.patterns_mode=mode
                    queries=[]
                    def counted(*args):
                        queries.append(args[2])
                    event.listen(db.engine.sync_engine,"before_cursor_execute",counted)
                    start=time.perf_counter()
                    success=True
                    try:
                        await collect(db,fixture)
                    except DatabaseUnavailable:
                        success=False
                    finally:
                        seconds=time.perf_counter()-start
                        event.remove(db.engine.sync_engine,"before_cursor_execute",counted)
                    async with db.engine.connect() as c:
                        committed=(await c.execute(text("SELECT count(*) FROM normalized_observations WHERE superseded_at IS NULL"))).scalar_one()
                    assert committed==(size if success else 0)
                    measurements.append(dict(implementation=label,records=size,trial=trial,
                        deadline_seconds=db.timeout,collection_seconds=round(seconds,6),
                        per_record_ms=round(seconds*1000/size,6) if success else None,
                        queries_attempted=len(queries),succeeded=success,committed_assertions=committed))
                    # No timing target beyond the specified default-deadline case.
                    if size==500 and label.startswith("corrected"):
                        assert success,measurements[-1]
        Path("/tmp/collection-performance.json").write_text(json.dumps({
            "baseline_m1_sha":"52db568d6b28cc7716c9329be396786906f65072",
            "baseline_m2_sha":"9ee41f1428ffe245f43e9dcc3763c9672cb80fb8",
            "default_collection_timeout_seconds":3,
            "note":"Same current schema/instance; two fresh-table trials per implementation/size. Failed deadlines and rolled-back assertions are retained. Per-record equivalent is only reported for complete collections. Shadow collection excludes deferred M2 enrichment.",
            "measurements":measurements},indent=2)+"\n")
        print("Collection benchmark complete; all failed measurements retained.")
    finally:
        await db.close()


if __name__=="__main__":
    asyncio.run(main())
