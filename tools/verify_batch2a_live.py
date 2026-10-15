"""Real upstream collection evidence; optional persistence ONLY to a disposable *_test DB."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from pec.sources.contracts import CONTRACTS
from pec.sources.environment_contracts import ENVIRONMENT_CONTRACTS, history_contract
from pec.sources.environment_models import EnvironmentalFact
from pec.sources.http import Client
from pec.sources.fetch import fetch


async def run(args):
    agent = "PhotographyEventsCore (+https://github.com/Tmatz27/photography-events-core)"
    database = None
    if args.database:
        from pec.config import Settings
        from pec.database import Database

        settings = Settings.from_env()
        if not make_url(settings.database_url).database.endswith("_test"):
            raise ValueError("Batch 2A verification NEVER writes an installed/live database")
        database = Database(settings)
        await database.ready()
    report = dict(
        started_at=datetime.now(UTC).isoformat(),
        genuine_network=True,
        disposable_postgis=bool(database),
        installed_database_modified=False,
        items=[],
    )
    try:
        for key in args.sources.split(","):
            if key not in ENVIRONMENT_CONTRACTS:
                raise ValueError("Unimplemented Batch 2A source")
            variants = [CONTRACTS[key]]
            if args.history and key in ("usgs_water", "cdec_river", "cdec_rainfall", "cdec_snow"):
                variants.append(history_contract(CONTRACTS[key]))
            for contract in variants:
                now = datetime.now(UTC)
                item = dict(source=contract.source_key)
                if database:
                    from pec.sources.ownership import collect_owned

                    status, retry = await collect_owned(database, contract, agent)
                    item.update(http_outcome=status, retry_after=retry)

                    async def inspect(c):
                        row = (
                            (
                                await c.execute(
                                    text("""SELECT r.status,r.incomplete,r.records_received,
                            r.records_accepted,r.records_rejected,r.error_code,r.requests,r.provider_updated_at,
                            r.completed_at,r.native_evidence_asof,p.checkpoint FROM source_runs r JOIN sources s ON s.id=r.source_id
                            JOIN source_poll_state p ON p.source_id=s.id WHERE s.key=:key ORDER BY r.id DESC LIMIT 1"""),
                                    dict(key=contract.source_key),
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assertions = (
                            (
                                await c.execute(
                                    text("""SELECT e.* FROM environmental_assertions e
                            JOIN source_runs r ON r.id=e.source_run_id JOIN sources s ON s.id=r.source_id
                            WHERE s.key=:key"""),
                                    dict(key=contract.source_key),
                                )
                            )
                            .mappings()
                            .all()
                        )
                        for assertion in assertions:
                            if assertion["numeric_value"] is not None:
                                assert assertion["numeric_value"] == Decimal(assertion["native_value"])
                            assert assertion["evidence_kind"] not in ("species", "behavior", "condition")
                            assert assertion["metadata"]["upstream_lineage"] == key
                        return dict(row), assertions

                    row, assertions = await database.pattern_transaction(inspect)
                    item.update(
                        database=dict(row),
                        persisted_assertions=len(assertions),
                        persisted_numeric_values=sum(v["numeric_value"] is not None for v in assertions),
                        native_units=sorted({v["unit"] for v in assertions if v["unit"]}),
                        evidence_kinds=sorted({v["evidence_kind"] for v in assertions}),
                        native_values_verified=bool(assertions),
                        collection_verified=status == 200 and not row["incomplete"] and row["requests"] > 0,
                        persistence_verified=bool(assertions),
                    )
                else:
                    client = Client(contract, agent)
                    client.provider_secrets = {}
                    try:
                        batch = await fetch(contract, client, now)
                    finally:
                        await client.close()
                    records = [r for r in batch.records if isinstance(r, EnvironmentalFact)]
                    digest = hashlib.sha256(
                        json.dumps([r.payload for r in records], sort_keys=True).encode()
                    ).hexdigest()
                    item.update(
                        http_outcome=batch.http_status,
                        complete=batch.complete,
                        received=batch.received,
                        accepted=len(records),
                        rejected=batch.rejected,
                        failure_code=batch.failure_code,
                        requests=batch.requests,
                        bytes_received=batch.bytes_received,
                        payload_sha256=digest,
                        native_units=sorted({r.unit for r in records if r.unit}),
                        evidence_kinds=sorted({r.evidence_kind for r in records}),
                        sample_times=[
                            dict(
                                observed_at=r.observed_at,
                                provider_updated_at=r.provider_updated_at,
                                valid_at=r.valid_at,
                                issued_at=r.issued_at,
                            )
                            for r in records[:2]
                        ],
                        collection_verified=batch.complete and batch.requests > 0,
                        persistence_verified=False,
                    )
                report["items"].append(item)
                print(json.dumps(item, default=str))
    finally:
        report["completed_at"] = datetime.now(UTC).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
        if database:
            await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--sources", default=",".join(ENVIRONMENT_CONTRACTS))
    parser.add_argument("--output", type=Path, default=Path("/tmp/batch2a-live.json"))
    asyncio.run(run(parser.parse_args()))
