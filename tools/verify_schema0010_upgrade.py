"""CI-only exact data/state comparison across 0009 -> 0010 in a disposable DB."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from pec.config import Settings

RECEIPT = Path("/tmp/schema0010-upgrade.json")
PROBE = "deployment-upgrade-probe"


def require_disposable(url, github_actions):
    parsed = make_url(url)
    if (
        github_actions != "true"
        or parsed.drivername != "postgresql+asyncpg"
        or not (parsed.database or "").endswith("_test")
    ):
        raise ValueError("Only a disposable GitHub Actions test database is allowed")


def quoted(name):
    if not re.fullmatch("[a-z_][a-z0-9_]*", name):
        raise ValueError("Unexpected schema identifier")
    return '"' + name + '"'


async def snapshot(c, baseline=None):
    if baseline is None:
        tables = (
            (
                await c.execute(
                    text("""SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'
            AND table_name NOT IN ('alembic_version','spatial_ref_sys') ORDER BY table_name""")
                )
            )
            .scalars()
            .all()
        )
        baseline = {}
        for table in tables:
            columns = (
                (
                    await c.execute(
                        text("""SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:name ORDER BY ordinal_position"""),
                        dict(name=table),
                    )
                )
                .scalars()
                .all()
            )
            baseline[table] = dict(columns=columns)
    result = {}
    for table, record in baseline.items():
        columns = ",".join(quoted(name) for name in record["columns"])
        rows = (
            (
                await c.execute(
                    text(
                        f"SELECT to_jsonb(t)::text FROM (SELECT {columns} FROM public.{quoted(table)}) t ORDER BY to_jsonb(t)::text"
                    )
                )
            )
            .scalars()
            .all()
        )
        result[table] = dict(
            columns=record["columns"],
            rows=len(rows),
            sha256=hashlib.sha256("\n".join(rows).encode()).hexdigest(),
        )
    return result


async def main(mode):
    settings = Settings.from_env()
    require_disposable(settings.database_url, os.environ.get("GITHUB_ACTIONS"))
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as c:
            revision = (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            if mode == "before":
                assert revision == "0009"
                sid = (
                    await c.execute(
                        text("""INSERT INTO sources(key,name,source_type)
                    VALUES(:key,'CI upgrade state sentinel','fixture') RETURNING id"""),
                        dict(key=PROBE),
                    )
                ).scalar_one()
                await c.execute(
                    text("""INSERT INTO source_poll_state(source_id,lease_token,lease_until,checkpoint)
                    VALUES(:sid,'11111111-1111-4111-8111-111111111111','2099-01-01',
                    CAST(:checkpoint AS jsonb))"""),
                    dict(
                        sid=sid,
                        checkpoint=json.dumps(
                            dict(station_index=2, next_start="2026-01-03T00:00:00Z", preserve=True)
                        ),
                    ),
                )
                await c.execute(text("INSERT INTO source_backoff VALUES(:sid,'2099-01-02',3)"), dict(sid=sid))
                tables = await snapshot(c)
                owner = (
                    await c.execute(
                        text("SELECT datdba::bigint FROM pg_database WHERE datname=current_database()")
                    )
                ).scalar_one()
                report = dict(
                    before_revision=revision,
                    disposable_database=True,
                    installed_database_modified=False,
                    probe_source_id=sid,
                    database_owner_oid=owner,
                    before=tables,
                )
            else:
                assert revision == "0010"
                report = json.loads(RECEIPT.read_text())
                after = await snapshot(c, report["before"])
                assert after == report["before"], (
                    "Existing data, privacy, revisions or collector state changed"
                )
                assert (
                    await c.execute(
                        text("SELECT datdba::bigint FROM pg_database WHERE datname=current_database()")
                    )
                ).scalar_one() == report["database_owner_oid"]
                assert (
                    await c.execute(text("SELECT count(*) FROM environmental_assertions"))
                ).scalar_one() == 0
                assert not (
                    await c.execute(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM source_runs WHERE native_evidence_asof IS NOT NULL)"
                        )
                    )
                ).scalar_one()
                # Remove only this isolated test sentinel after proving its lease,
                # checkpoint and failure state survived. Legacy checks stay intact.
                await c.execute(
                    text("DELETE FROM sources WHERE id=:sid AND key=:key"),
                    dict(sid=report["probe_source_id"], key=PROBE),
                )
                report.update(
                    after_revision=revision,
                    after=after,
                    existing_rows_identical=True,
                    collector_state_preserved=True,
                    database_owner_preserved=True,
                    new_environment_history_empty=True,
                    migration_0010_metadata_nullable=True,
                    probe_removed_after_verification=True,
                )
        RECEIPT.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                dict(
                    stage=mode,
                    revision=revision,
                    tables=len(report["before"]),
                    installed_database_modified=False,
                )
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("before", "after"))
    asyncio.run(main(parser.parse_args().mode))
