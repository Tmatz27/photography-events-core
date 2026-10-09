"""F4 real PostGIS measurement, only disposable *_test DB; no redesign."""

import asyncio
import json
import statistics
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from pec.config import Settings
from pec.database import Database
from pec.sources.contracts import CONTRACTS
from pec.sources.models import Batch
from pec.sources.storage import SOURCE_FINGERPRINT_SQL, source_fingerprint, register, persist


def scans(node):
    answer = []
    if node.get("Relation Name") == "raw_observations":
        loops = node.get("Actual Loops", 1)
        answer.append(
            dict(
                node_type=node["Node Type"],
                rows_returned=node.get("Actual Rows", 0) * loops,
                rows_filtered=node.get("Rows Removed by Filter", 0) * loops,
                loops=loops,
                shared_hit_blocks=node.get("Shared Hit Blocks", 0),
            )
        )
    for child in node.get("Plans", []):
        answer.extend(scans(child))
    return answer


async def main():
    settings = Settings.from_env()
    url = make_url(settings.database_url)
    assert url.database.endswith("_test"), "Disposable test database only"
    db = Database(settings)
    output = dict(
        shadow_transaction_budget_seconds=db.pattern_timeout,
        scheduled_poll_budget_seconds=120,
        method="Three fingerprint trials and three full empty/failed persist trials per source/size, all sources seeded simultaneously; EXPLAIN ANALYZE BUFFERS; no index/partition/retention changes",
        measurements=[],
    )
    now = datetime.now(UTC)
    try:
        for size in (1000, 10000, 25000):

            async def seed(c):
                await c.execute(
                    text(
                        "TRUNCATE sources,locations,assessment_runs,observation_report_groups RESTART IDENTITY CASCADE"
                    )
                )
                ids = {}
                for key, contract in CONTRACTS.items():
                    sid = await register(c, contract)
                    ids[key] = sid
                    await c.execute(
                        text("""INSERT INTO raw_observations(source_id,external_id,observed_at,fetched_at,
                        parser_version,content_sha256,sensitive,provider_updated_at,state_poll_started_at,retired_at,retirement_reason)
                        SELECT :sid,'retained-'||lpad(i::text,12,'0'),CAST(:old AS timestamptz),CAST(:old AS timestamptz),'benchmark',repeat('a',64),i%3=0,CAST(:old AS timestamptz),CAST(:old AS timestamptz),
                        CASE WHEN i%2=0 THEN CAST(:old AS timestamptz) ELSE NULL END,CASE WHEN i%2=0 THEN 'snapshot_absent' ELSE NULL END
                        FROM generate_series(1,CAST(:size AS integer)) i"""),
                        dict(sid=sid, old=now - timedelta(days=60), size=size),
                    )
                await c.execute(text("ANALYZE raw_observations"))
                return ids

            ids = await db.pattern_transaction(seed, write=True)
            for key, sid in ids.items():
                samples = []
                digests = []
                for _ in range(3):
                    begin = time.perf_counter()
                    digests.append(await db.pattern_transaction(lambda c: source_fingerprint(c, sid)))
                    samples.append(time.perf_counter() - begin)
                assert len(set(digests)) == 1

                async def explain(c):
                    return (
                        await c.execute(
                            text("EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) " + SOURCE_FINGERPRINT_SQL),
                            dict(sid=sid),
                        )
                    ).scalar_one()

                plan = await db.pattern_transaction(explain)
                whole = []
                for trial in range(3):
                    begin = time.perf_counter()
                    stamp = now + timedelta(seconds=trial)
                    await persist(db, CONTRACTS[key], Batch(complete=False), stamp, stamp)
                    whole.append(time.perf_counter() - begin)
                entry = dict(
                    source=key,
                    retained_rows_per_source=size,
                    total_raw_rows=size * len(ids),
                    fingerprint_seconds=samples,
                    fingerprint_median_seconds=statistics.median(samples),
                    full_persist_seconds=whole,
                    full_persist_median_seconds=statistics.median(whole),
                    source_rows_returned=size,
                    raw_scan_rows=scans(plan[0]["Plan"]),
                    explain=plan,
                )
                output["measurements"].append(entry)
        output["max_fingerprint_seconds"] = max(max(x["fingerprint_seconds"]) for x in output["measurements"])
        output["max_full_persist_seconds"] = max(
            max(x["full_persist_seconds"]) for x in output["measurements"]
        )
        output["optimization_required"] = output["max_full_persist_seconds"] >= db.pattern_timeout * 0.5
        Path("/tmp/source-fingerprint-performance.json").write_text(json.dumps(output, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: output[k]
                    for k in ("max_fingerprint_seconds", "max_full_persist_seconds", "optimization_required")
                }
            )
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
