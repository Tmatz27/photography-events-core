"""Real PostGIS H3 history-cliff replay and untruncated query-plan receipts."""
import asyncio
import importlib.util
import json
import time
from pathlib import Path

from sqlalchemy import text

from pec.config import Settings
from pec.database import Database, DatabaseUnavailable
from pec.ingestion import collect_fixture
from pec.patterns import engine, identity
from pec.patterns.clustering import input_window
from pec.patterns.policy import POLICIES

OUT=Path("/tmp/h3-performance.json")


def historical():
    path=Path("/tmp/collection-baselines/h3-identity.py")
    spec=importlib.util.spec_from_file_location("h3_legacy_identity",path)
    module=importlib.util.module_from_spec(spec)
    module.__package__="pec.patterns"
    spec.loader.exec_module(module)
    return module


async def main():
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
    from test_database import NOW
    from test_h3 import data, generate, records, reset, seed_history
    db=Database(Settings.from_env())
    assert db.engine.url.database.endswith("_test"),"Disposable DB only"
    assert db.timeout==3 and db.pattern_timeout==30
    results={"baseline_sha":"c1db87e6c7a828d33e19a8ee91683998b4f3bb58",
             "collection_deadline":3,"enrichment_server_transaction_ms":900,"cases":[]}
    legacy=historical()
    try:
        for size in (0,2000,5000,10000,25000):
            await reset(db)
            await collect_fixture(db,data(sightings=records(4)))
            if size:
                await seed_history(db,size)
            # Replay the old enrichment against the same server/default budget.
            # No timing hard requirement is imposed on this machine's old cliff.
            async def old(c):
                await engine.server_bounds(c,1.0)
                return await legacy.reconcile(c,NOW)
            start=time.perf_counter()
            try:
                await db.pattern_transaction(old,write=True,repeatable=True,timeout=1)
                baseline={"status":"completed","seconds":round(time.perf_counter()-start,6)}
            except DatabaseUnavailable:
                baseline={"status":"failed_at_default_budget","seconds":round(time.perf_counter()-start,6)}
            prepared=[]
            original=identity.working_set
            async def counted(*args):
                found=await original(*args)
                prepared.append(len(found))
                return found
            identity.working_set=counted
            try:
                result,run,elapsed=await generate(db)
            finally:
                identity.working_set=original
            case={"retained_old":size,"old_enrichment":baseline,"shadow_status":run["status"],
                  "shadow_completion_seconds":round(elapsed,6),"working_set_rows":prepared}
            if size in (0,10000,25000):
                async with db.engine.begin() as c:
                    rows=await identity.working_set(c,NOW,POLICIES)
                    keys=json.dumps([dict(namespace=ns,origin=origin)
                                     for ns,origin in sorted(identity.dependency_keys(rows))])
                    plans={}
                    for name,query,params in (
                        ("active",identity.ACTIVE_SQL,input_window(NOW,POLICIES)),
                        ("dependencies",identity.DEPENDENCY_SQL,{"keys":keys}),
                        ("retirement",identity.RETIRE_SQL,{"now":NOW,"raw_ids":[r["raw_observation_id"] for r in rows]}),
                    ):
                        plans[name]=(await c.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "+query),params)).scalar_one()
                    case["plans"]=plans
            results["cases"].append(case)
            OUT.write_text(json.dumps(results,indent=2)+"\n")
        assert all(c["working_set_rows"]==[4] and c["shadow_status"]=="published" for c in results["cases"])
        print("H3: 4-row working set publishes with 0/2000/5000/10000/25000 old assertions; full plans saved.")
    finally:
        OUT.write_text(json.dumps(results,indent=2)+"\n")
        await db.close()


if __name__=="__main__":
    asyncio.run(main())
