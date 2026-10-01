"""Semantic equality with captured real legacy execution, not shape equality."""
import json
from pathlib import Path

import pytest

from pec.phenomena import evaluate

FIXTURE = json.loads((Path(__file__).parent / "fixtures/legacy_tule_elk.json").read_text(encoding="utf-8"))


def normalize(item):
    data = item.model_dump(mode="json")
    data["starts_at"] = item.starts_at.isoformat()
    data["ends_at"] = item.ends_at.isoformat()
    data["cant_miss"] = item.eligibility
    return data


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_legacy_semantic_parity(case):
    actual = evaluate(case["input"])
    assert len(actual) == len(case["expected"])
    for item, expected in zip(actual, case["expected"], strict=True):
        fields = normalize(item)
        assert {name: fields[name] for name in expected} == expected


def test_identity_survives_recalculation():
    case = next(c["input"] for c in FIXTURE["cases"] if c["name"] == "elk_recent_presence")
    before = evaluate(case)[0]
    after = evaluate({**case, "now": "2026-09-28T17:00:00+00:00", "alerts": None})[0]
    assert before.occurrence_key == after.occurrence_key
    assert before.eligibility and not after.eligibility
    assert before.definition_hash == after.definition_hash
