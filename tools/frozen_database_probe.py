"""R19: actual asyncpg pool + API under Docker pause, then unpause recovery."""
import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx

from pec.api import create_app
from pec.config import Settings
from pec.database import Database

ROOT = Path("/tmp")


async def wait_file(name):
    async with asyncio.timeout(30):
        while not (ROOT / name).exists():
            await asyncio.sleep(0.05)


async def main():
    settings = replace(Settings.from_env(), database_timeout=2)
    db = Database(settings)
    await asyncio.gather(*(db.ready() for _ in range(5)))
    (ROOT / "frozen-ready").touch()
    await wait_file("frozen-go")
    app = create_app(settings, db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as client:
        async def request(index):
            start = asyncio.get_running_loop().time()
            path = ["/health/ready", "/api/v1/opportunities", "/api/v1/sources/health"][index % 3]
            response = await client.get(path, headers={"Authorization": "Bearer " + settings.api_token})
            elapsed = asyncio.get_running_loop().time() - start
            assert response.status_code == 503, response.status_code
            assert elapsed <= settings.database_timeout + 1, elapsed
            return round(elapsed, 4)
        durations = await asyncio.wait_for(asyncio.gather(*(request(i) for i in range(8))), 5)
        assert db.engine.pool.checkedout() == 0, db.engine.pool.status()
        result = {"requests": 8, "deadline": 2, "seconds": durations, "checked_out_after_failure": 0}
        (ROOT / "frozen-results.json").write_text(json.dumps(result))
        (ROOT / "frozen-done").touch()
        await wait_file("frozen-recover")
        for _ in range(20):
            try:
                await db.ready()
                break
            except Exception:
                await asyncio.sleep(0.2)
        else:
            raise AssertionError("Pool did not recover")
        assert db.engine.pool.checkedout() == 0
        result["recovered"] = True
        (ROOT / "frozen-results.json").write_text(json.dumps(result))
    await db.close()
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
