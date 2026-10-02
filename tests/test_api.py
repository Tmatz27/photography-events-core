import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from pec.api import create_app
from pec.config import Settings
from pec.database import DatabaseUnavailable, envelope, project_source
from pec.phenomena import evaluate
from pec.schemas import SourceHealth

TOKEN = "test-only-" + "a" * 40
NOW = datetime.fromisoformat("2026-09-27T17:00:00+00:00")
DATA = next(c["input"] for c in json.loads((Path(__file__).parent / "fixtures/legacy_tule_elk.json").read_text())['cases'] if c['name'] == 'elk_recent_presence')
SETTINGS = Settings("postgresql+asyncpg://fixture:fixture@localhost/fixture", TOKEN)


class FakeDatabase:
    def __init__(self, fail=False, empty=False, stale=False):
        self.fail, self.empty, self.stale = fail, empty, stale

    async def ready(self):
        if self.fail:
            raise DatabaseUnavailable()

    async def health(self, now):
        await self.ready()
        return [SourceHealth(key=k, state="STALE" if self.stale else "UP", last_attempt_at=NOW,
                last_success_at=NOW, provider_updated_at=NOW, error_code=None)
                for k in ("nws_alerts", "fixture_observations")]

    async def opportunities(self, now, presentation=None, category=None, occurrence_key=None):
        await self.ready()
        items = [] if self.empty else evaluate(DATA)
        if occurrence_key:
            items = [i for i in items if i.occurrence_key == occurrence_key]
        return envelope(dict(data_as_of=NOW, valid_until=NOW + timedelta(hours=3), state="complete"),
                        items, await self.health(now), now, presentation, category)

    async def close(self):
        pass


@pytest.fixture
def app():
    return create_app(SETTINGS, FakeDatabase(), lambda: NOW)


async def get(app, path, token=TOKEN):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as c:
        return await c.get(path, headers={b"Authorization": ("Bearer " + token).encode()} if token is not None else {})


@pytest.mark.parametrize("path", ["/api/v1/opportunities", "/api/v1/opportunities/test", "/api/v1/sources/health"])
@pytest.mark.parametrize("token", [None, "wrong", "nonascii-é"])
async def test_auth(app, path, token):
    r = await get(app, path, token)
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "unauthorized", "message": "Authentication required"}}
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
async def test_health_metadata(app, path):
    r = await get(app, path, None)
    assert r.status_code == 200
    assert r.json()["api_version"] == "v1"
    assert r.json()["schema_version"] == "0002"


@pytest.mark.parametrize("path", ["/health/ready", "/api/v1/opportunities", "/api/v1/opportunities/test", "/api/v1/sources/health"])
async def test_database_failure_is_503(path):
    app = create_app(SETTINGS, FakeDatabase(fail=True))
    r = await get(app, path)
    assert r.status_code == 503 and "items" not in r.json()
    assert (await get(app, "/health/live")).status_code == 200


async def test_filters_and_detail(app):
    result = (await get(app, "/api/v1/opportunities?presentation=cant_miss&category=mammals")).json()
    assert len(result["items"]) == 1
    key = result["items"][0]["occurrence_key"]
    assert (await get(app, "/api/v1/opportunities/" + key)).json() == result["items"][0]
    assert (await get(app, "/api/v1/opportunities?category=birds")).json()["items"] == []
    assert (await get(app, "/api/v1/opportunities/no-such-occurrence")).status_code == 404


@pytest.mark.parametrize("query", ["presentation=bad", "category=bad"])
async def test_invalid_query_is_consistent(app, query):
    r = await get(app, "/api/v1/opportunities?" + query)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("stale,expected", [(False, "complete"), (True, "incomplete")])
async def test_empty_is_not_incomplete(stale, expected):
    app = create_app(SETTINGS, FakeDatabase(empty=True, stale=stale), lambda: NOW)
    result = (await get(app, "/api/v1/opportunities")).json()
    assert result["items"] == [] and result["assessment_state"] == expected


async def test_stale_data_loses_eligibility():
    app = create_app(SETTINGS, FakeDatabase(), lambda: NOW + timedelta(days=1))
    result = (await get(app, "/api/v1/opportunities")).json()
    assert result["assessment_state"] == "incomplete"
    assert result["items"][0]["presentation"] == "held"
    assert not result["items"][0]["eligibility"]


def test_no_assessment_is_incomplete():
    assert envelope(None, [], [], NOW).assessment_state == "incomplete"


@pytest.mark.parametrize("status,age,expected", [("success", 0, "UP"), ("success", 4, "STALE"), ("failure", 0, "DOWN")])
def test_source_projection(status, age, expected):
    row = dict(key="nws_alerts", enabled=True, status=status, provider_updated_at=NOW - timedelta(hours=age),
               last_success_at=NOW, last_attempt_at=NOW, error_code=None)
    assert project_source(row, NOW).state == expected


def test_configuration_and_redaction(monkeypatch):
    assert TOKEN not in repr(SETTINGS)
    monkeypatch.setenv("CORE_DATABASE_URL", "postgresql+asyncpg://a:b@db/test")
    monkeypatch.setenv("CORE_API_TOKEN", TOKEN)
    assert Settings.from_env().api_token == TOKEN
    with pytest.raises(ValueError):
        Settings("sqlite://", TOKEN)
    with pytest.raises(ValueError):
        Settings(SETTINGS.database_url, "short")
    with pytest.raises(ValueError):
        Settings(SETTINGS.database_url, TOKEN, database_timeout=300)


def test_openapi_is_strongly_typed(app):
    schema = app.openapi()
    assert len(schema["paths"]) == 5
    assert schema["paths"]["/api/v1/opportunities"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "Opportunity" in schema["components"]["schemas"]
    assert "exact_geometry" not in json.dumps(schema)
    assert TOKEN not in json.dumps(schema)
