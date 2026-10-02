"""Independent pinned legacy evaluator fuzz and pipeline oracle capture."""
import argparse
import copy
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from capture_legacy_parity import BASE_SHA, cases, load_legacy, normalize


def legacy_result(data, modules, *, pipeline=False):
    events, eligibility, wildlife, _, _, _, event_state, _ = modules
    now = datetime.fromisoformat(data["now"])
    sightings = [wildlife.Sighting(species=s.get("species", s["scientific_name"]),
        scientific_name=s["scientific_name"], place=s.get("place") or "Synthetic fixture only",
        latitude=s["latitude"], longitude=s["longitude"],
        latest=datetime.fromisoformat(s["observed_at"]), earliest=datetime.fromisoformat(s["observed_at"]),
        source=s.get("source", "iNaturalist"), category="mammals", reports=1,
        observers=s.get("observers", []), count=s.get("count"), private_location=s.get("private_location", False))
        for s in data["sightings"]]
    if pipeline:
        sightings = wildlife.digest(sightings, now, 14 * 24)
    items = [item for item in events.build_seasonal_opportunities(now, data["horizon_days"],
             tuple(data["home"]), sightings) if item.phenomenon == "tule_elk_rut"]
    eligibility.annotate(items, now, max_drive_hours=data["max_drive_hours"], alerts=data["alerts"])
    return [normalize(item, now, eligibility, event_state) for item in items]


def pipeline_cases(modules):
    base = next(c["input"] for c in cases() if c["name"] == "elk_recent_presence")
    now = datetime.fromisoformat(base["now"])
    one = base["sightings"][0]
    def step(hours=0, **changes):
        return {**copy.deepcopy(base), "now": (now + timedelta(hours=hours)).isoformat(), **changes}
    variants = [
        ("normal", [step()]),
        ("private", [step(sightings=[{**one, "private_location": True}])]),
        ("future_inside_grace", [step(sightings=[{**one, "observed_at": (now + timedelta(minutes=30)).isoformat()}])]),
        ("future_waits_without_refetch", [
            step(sightings=[{**one, "observed_at": (now + timedelta(hours=2)).isoformat()}]),
            step(1.1, sightings=[])]),
        ("incremental_empty_batch", [step(), step(24, sightings=[])]),
        ("corrected_timestamp", [step(), step(1, sightings=[{**one, "observed_at": (now - timedelta(days=20)).isoformat()}])]),
        ("corrected_coordinates", [step(), step(1, sightings=[{**one, "latitude": 40, "longitude": -123}])]),
        ("corrected_species", [step(), step(1, sightings=[{**one, "scientific_name": "Cervus elaphus"}])]),
        ("legacy_place_grouping", [step(sightings=[one, {**one, "external_id": "second", "latitude": 40,
            "observed_at": (now - timedelta(days=1)).isoformat()}])]),
    ]
    result = []
    for name, steps in variants:
        current, captured = {}, []
        for data in steps:
            for record in data["sightings"]:
                current[record["external_id"]] = record
            logical = {**data, "sightings": list(current.values())}
            captured.append({"input": data, "expected": legacy_result(logical, modules, pipeline=True)})
        result.append({"name": name, "steps": captured})
    return {"legacy_sha": BASE_SHA, "synthetic": True,
            "pipeline": "digest(raw, now, 14*24) -> build_seasonal_opportunities -> annotate", "cases": result}


def fuzz(modules, count):
    from pec.phenomena import evaluate
    randomizer = random.Random(20261001)
    base = next(c["input"] for c in cases() if c["name"] == "elk_recent_presence")
    for index in range(count):
        now = datetime(2026, 1, 1, 17, tzinfo=UTC) + timedelta(days=randomizer.randrange(730))
        data = {**base, "now": now.isoformat(), "horizon_days": randomizer.choice([0, 7, 60, 120, 365, 366]),
                "max_drive_hours": randomizer.choice([0.5, 1, 2, 6]),
                "alerts": randomizer.choice([[], None, [{"event": "High Wind Warning", "onset": now.isoformat(),
                    "ends": (now + timedelta(days=1)).isoformat(), "same": ["006079"]}]])}
        data["sightings"] = [{**base["sightings"][0], "external_id": str(n),
            "observed_at": (now - timedelta(hours=randomizer.randint(-48, 24 * 25))).isoformat(),
            "latitude": randomizer.choice([35.2, 35.4, 38.5]), "longitude": randomizer.choice([-119.8, -123.1]),
            "scientific_name": randomizer.choice(["Cervus canadensis nannodes", "Cervus elaphus"]),
            "private_location": randomizer.choice([True, False])} for n in range(randomizer.randrange(4))]
        expected = legacy_result(data, modules)
        actual = evaluate(data)
        assert len(actual) == len(expected), index
        for item, wanted in zip(actual, expected, strict=True):
            got = item.model_dump(mode="json")
            got.update(starts_at=item.starts_at.isoformat(), ends_at=item.ends_at.isoformat(), cant_miss=item.eligibility)
            assert {k: got[k] for k in wanted} == wanted, f"Evaluator mismatch at deterministic case {index}"
    return {"seed": 20261001, "comparisons": count, "mismatches": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=18000)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    modules = load_legacy(args.legacy_repo)
    result = pipeline_cases(modules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {"legacy_sha": BASE_SHA, "pipeline_cases": len(result["cases"]), "evaluator": fuzz(modules, args.count)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
