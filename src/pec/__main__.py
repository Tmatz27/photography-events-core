"""Explicit development-only fixture import. Never seeds a production startup."""
import argparse
import asyncio
import json
from pathlib import Path

from .config import Settings
from .database import Database
from .ingestion import ingest_fixture


async def run(args):
    db = Database(Settings.from_env())
    try:
        await db.ready()
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        data = next(c["input"] for c in fixture["cases"] if c["name"] == args.case)
        items = await ingest_fixture(db, data)
        print(f"Stored {len(items)} synthetic fixture opportunity(s); not live recommendations.")
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--case", default="elk_recent_presence")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
