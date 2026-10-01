"""Execute the pinned HA engine, freezing logical inputs and normalized outcomes.

Never import Core here: expected results must come from the legacy code alone.
Usage: python tools/capture_legacy_parity.py --legacy-repo ../Home-assistant-photography-events
"""
import argparse
import hashlib
import importlib
import json
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

BASE_SHA = "4905e35c0668c37737d84685e65d2a806f7c92f7"


def load_legacy(root):
    actual = subprocess.check_output(["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != BASE_SHA:
        raise SystemExit(f"Capture requires baseline {BASE_SHA}; got {actual}")
    package = types.ModuleType("photography_events")
    package.__path__ = [str(root / "custom_components/photography_events")]
    sys.modules[package.__name__] = package
    return [importlib.import_module(f"photography_events.{name}") for name in
            ("events", "eligibility", "wildlife", "phenomena", "curation", "gear", "event_state", "birds")]


def cases():
    base = {"now": "2026-09-27T17:00:00+00:00", "horizon_days": 60,
            "max_drive_hours": 6.0, "home": [34.742, -120.5724], "alerts": [],
            "sightings": [], "phenomenon": "tule_elk_rut"}
    observation = {"species": "Tule elk", "scientific_name": "Cervus canadensis nannodes",
                   "latitude": 35.20, "longitude": -119.80, "observed_at": "2026-09-25T17:00:00+00:00",
                   "source": "iNaturalist", "external_id": "fixture-elk-1", "observers": ["fixture-a"],
                   "count": 1, "private_location": False}
    variants = [
        ("elk_no_report", {}),
        ("elk_recent_presence", {"sightings": [observation]}),
        ("elk_stale_presence", {"sightings": [{**observation, "observed_at": "2026-09-10T17:00:00+00:00"}]}),
        ("elk_presence_day_10", {"sightings": [{**observation, "observed_at": "2026-09-17T17:00:00+00:00"}]}),
        ("elk_distant_presence", {"sightings": [{**observation, "latitude": 38.2, "longitude": -122.9}]}),
        ("elk_wrong_species", {"sightings": [{**observation, "scientific_name": "Cervus elaphus"}]}),
        ("elk_safety_unknown", {"sightings": [observation], "alerts": None}),
        ("elk_over_drive_limit", {"sightings": [observation], "max_drive_hours": 1.0}),
        ("elk_unsafe", {"sightings": [observation], "alerts": [{"event": "High Wind Warning",
          "onset": "2026-09-27T10:00:00+00:00", "ends": "2026-09-29T10:00:00+00:00", "same": ["006079"]}]}),
        ("elk_next_year", {"now": "2027-09-27T17:00:00+00:00"}),
        ("elk_approaching", {"now": "2026-09-12T17:00:00+00:00"}),
        ("elk_beyond_week", {"now": "2026-09-01T17:00:00+00:00"}),
        ("elk_season_precision", {"now": "2026-06-01T17:00:00+00:00", "horizon_days": 365}),
        ("elk_after_season", {"now": "2026-10-11T17:00:00+00:00"}),
        ("elk_end_window", {"now": "2026-10-10T17:00:00+00:00"}),
    ]
    return [{"name": name, "input": {**base, **changes}} for name, changes in variants]


def normalize(item, now, eligibility, event_state):
    a = item.extra["assessment"]
    board = eligibility.dashboard([item], now)
    return {
        "phenomenon_key": item.phenomenon, "occurrence_key": event_state.event_id(item),
        "starts_at": item.start.isoformat(), "ends_at": item.end.isoformat(),
        "eligibility": a["eligible"], "presentation": "watching" if a["presentation"] == "watch" else a["presentation"],
        "significance": a["significance"], "confidence": a["confidence"], "urgency": a["urgency"],
        "drive_minutes": round(item.drive_hours * 60, 4), "drive_basis": a["drive_basis"],
        "safety_state": a["safety_state"], "access_state": a["access_state"] or a["access"],
        "evidence_state": a["evidence_state"], "reason": a["why_now"],
        "awaiting": item.extra.get("awaiting", ""), "blockers": a["blockers"],
        "held": a["held"], "cant_miss": bool(board["events"]),
        "watching": any(row.get("event_id") == event_state.event_id(item) for row in board["watch"]),
        "gear": item.extra["gear_plan"], "ethics": item.extra.get("ethics", ""),
        "safety_summary": item.extra["safety_summary"], "safety_notes": item.extra["safety_notes"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures/legacy_tule_elk.json"))
    args = parser.parse_args()
    events, eligibility, wildlife, phenomena, curation, gear, event_state, birds = load_legacy(args.legacy_repo)
    fixtures = cases()
    for case in fixtures:
        data = case["input"]
        now = datetime.fromisoformat(data["now"])
        sightings = [wildlife.Sighting(species=s["species"], scientific_name=s["scientific_name"],
            place="Synthetic fixture only", latitude=s["latitude"], longitude=s["longitude"],
            latest=datetime.fromisoformat(s["observed_at"]), earliest=datetime.fromisoformat(s["observed_at"]),
            source=s["source"], category="mammals", reports=1, observers=s["observers"], count=s["count"])
            for s in data["sightings"]]
        items = [item for item in events.build_seasonal_opportunities(
            now, data["horizon_days"], tuple(data["home"]), sightings) if item.phenomenon == data["phenomenon"]]
        eligibility.annotate(items, now, max_drive_hours=data["max_drive_hours"], alerts=data["alerts"])
        case["expected"] = [normalize(item, now, eligibility, event_state) for item in items]
    files = ["events.py", "phenomena.py", "eligibility.py", "curation.py", "event_state.py", "wildlife.py", "gear.py", "weather_hazards.py"]
    hashes = {name: hashlib.sha256((args.legacy_repo / "custom_components/photography_events" / name).read_bytes()).hexdigest() for name in files}
    result = {"legacy_sha": BASE_SHA, "source_hashes": hashes, "synthetic": True,
              "notes": "Inputs are synthetic; expected results executed against pinned real legacy engine.", "cases": fixtures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Captured {len(fixtures)} cases from {BASE_SHA}")


if __name__ == "__main__":
    main()

