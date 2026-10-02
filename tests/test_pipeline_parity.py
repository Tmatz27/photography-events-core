"""R18: raw fixture -> collection -> stored assertions -> publication -> API."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from pec.api import create_app
from pec.ingestion import ingest_fixture
from pec.schemas import Opportunity
from test_api import SETTINGS, get
from test_database import URL, db as database_fixture
from test_parity import normalize

db = database_fixture
pytestmark = [pytest.mark.database, pytest.mark.skipif(not URL, reason="Requires disposable PostGIS database")]
FIXTURE = json.loads((Path(__file__).parent / "fixtures/legacy_pipeline.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
async def test_r18_full_pipeline_parity(db, case):
    for step in case["steps"]:
        now = datetime.fromisoformat(step["input"]["now"])
        await ingest_fixture(db, step["input"])
        app = create_app(SETTINGS, db, lambda: now)
        response = await get(app, "/api/v1/opportunities")
        assert response.status_code == 200
        body = response.json()
        assert body["assessment_state"] == "complete"
        assert body["assessment_id"] is not None
        assert len(body["items"]) == len(step["expected"])
        for row, wanted in zip(body["items"], step["expected"], strict=True):
            actual = normalize(Opportunity.model_validate(row))
            assert {key: actual[key] for key in wanted} == wanted
            assert row["assessment_id"] == body["assessment_id"]
            assert "analysis_geometry" not in row and "exact_geometry" not in row
