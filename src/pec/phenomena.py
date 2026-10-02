"""Versioned Carrizo rule, ported from HA 0.16.1; no network or ORM dependency.

The initial vertical slice supports calendar plus species-presence evidence.
It deliberately does not claim to port the legacy report-text parser.
"""
import hashlib
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

from . import CORE_VERSION
from .legacy_safety import safety
from .schemas import Opportunity, PublicLocation
from .spatial import haversine_km

ROOT = Path(__file__).parent


def definition(key="tule_elk_rut"):
    if key != "tule_elk_rut":
        raise ValueError("Phenomenon not implemented in Milestone 1")
    path = ROOT / "definitions" / f"{key}.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    # Decision code AND descriptive rule data participate in provenance.
    for file in [path, ROOT / "phenomena.py", ROOT / "legacy_safety.py", ROOT / "spatial.py"]:
        digest.update(file.name.encode())
        digest.update(file.read_bytes().replace(b"\r\n", b"\n"))
    result["hash"] = digest.hexdigest()
    return result


def evaluate(data: dict) -> list[Opportunity]:
    return evaluate_with_evidence(data)[0]


def evaluate_with_evidence(data: dict):
    """Evaluate a bounded logical fixture using the production application layer.

An ingestion adapter supplies normalized species assertions, never final
opportunity JSON. Fetch timestamps are deliberately absent from evidence age.
"""
    d = definition(data.get("phenomenon", "tule_elk_rut"))
    now = datetime.fromisoformat(data["now"])
    if now.tzinfo is None:
        raise ValueError("An aware evaluation time is required")
    horizon_days = data.get("horizon_days", 60)
    if not 0 <= horizon_days <= 366:
        raise ValueError("horizon_days must be between 0 and 366")
    horizon = now.date() + timedelta(days=horizon_days)
    home = data.get("home", [34.742, -120.5724])
    drive = round(max(0.25, haversine_km(*home, d["latitude"], d["longitude"]) /
                      d["median_effective_speed_kmh"]), 2)
    limit = data.get("max_drive_hours", 6.0)
    presence = []
    for s in data.get("sightings", []):
        observed = datetime.fromisoformat(s["observed_at"])
        if (s["scientific_name"].lower().startswith("cervus canadensis nannodes")
                and observed >= now - timedelta(days=14)
                and haversine_km(d["latitude"], d["longitude"], s["latitude"], s["longitude"]) <= 120):
            presence.append(s)
    result, evidence = [], {}
    for year in sorted({now.year - 1, now.year, horizon.year, now.year + 1}):
        first, last = date(year, *d["peak_start"]), date(year, *d["peak_end"])
        if last < now.date() or first > horizon:
            continue
        days = (first - now.date()).days
        near = days <= 60
        start = datetime.combine(first, time.min, now.tzinfo)
        end = datetime.combine(last, time.max, now.tzinfo)
        underway = first <= now.date() <= last
        state = ("calendar_presence" if presence else "calendar") if near else "season"
        evidence[f"{d['key']}-{first.isoformat()}"] = sorted({
            nid for sighting in presence for nid in sighting.get("normalized_ids", [])
        }) if state == "calendar_presence" else []
        score = min(78 if underway else 65, 74 if presence else 70) if near else 45
        planning_only = not near or score <= 60
        awaiting = (
            "Too far out to confirm. Specifics and live corroboration start 60 days before the window opens."
            if not near else
            "Documented annual cycle and a recent report near the site. Conditions and access on the day still matter."
            if presence else
            "Documented annual cycle from the site's managers or monitors; conditions and access on the day still matter."
        )
        reason = ("Peak of the documented annual cycle, with a recent report near the site."
                  if state == "calendar_presence" else "Documented peak underway."
                  if state == "calendar" else "Season")
        checked = safety(SimpleNamespace(latitude=d["latitude"], longitude=d["longitude"],
                         drive_hours=drive, start=start, end=end), data.get("alerts"), now)
        blockers = []
        if state != "calendar_presence":
            blockers.append("encounter unconfirmed: needs a recent report of the animals near the site"
                            if state == "calendar" else "calendar reliable: " + awaiting)
        if start > now + timedelta(days=7):
            blockers.append("beyond the seven-day Can't Miss horizon")
        if drive > limit:
            blockers.append(f"beyond the {limit:g} h Can't Miss drive limit")
        if checked["unsafe"]:
            blockers.append(checked["summary"])
        unverified = [checked["summary"]] if checked["state"] == "unknown" and checked["travel"] else []
        held = bool(unverified) and not blockers
        blockers.extend(unverified)
        eligible = not blockers
        presentation = "cant_miss" if eligible else "watching" if state == "calendar" and not planning_only else "planner"
        urgency = (95 if end - now <= timedelta(hours=48) else 85) if start <= now <= end else (
            85 if start - now <= timedelta(hours=24) else 75 if start - now <= timedelta(hours=48)
            else 55 if start - now <= timedelta(days=7) else 20)
        # The product result is valid only while this safety check is current.
        # No stale observation is renewed by loading the same raw fixture again.
        validity = min(end, now + timedelta(hours=3))
        if state == "calendar_presence":
            validity = min(validity, max(datetime.fromisoformat(s["observed_at"]) for s in presence) + timedelta(days=14))
        result.append(Opportunity(
            occurrence_key=f"{d['key']}-{first.isoformat()}", phenomenon_key=d["key"],
            title=d["name"] if near else d["name"] + " (season)", category=d["category"],
            location=PublicLocation(key=d["location_key"], name=d["location_name"],
                                    latitude=d["latitude"], longitude=d["longitude"]),
            starts_at=start, ends_at=end, presentation=presentation, eligibility=eligible,
            significance=d["significance"], confidence={"calendar_presence": 78, "calendar": 70, "season": 10}[state],
            urgency=urgency, evidence_state=state, access_state="unsafe" if checked["unsafe"] else "public",
            safety_state=checked["state"], drive_minutes=round(drive * 60, 4), drive_basis="estimate",
            reason=reason, awaiting=awaiting, blockers=blockers, held=held,
            watching=presentation == "watching" and start <= now + timedelta(days=14),
            gear=d["gear"], ethics=d["ethics"], safety_summary=checked["summary"],
            safety_notes=[*checked["notes"], d["safety"]], best_time_of_day=d["best_time_of_day"],
            detail=d["photo_tips"], data_as_of=now, valid_until=validity,
            definition_key=d["key"], definition_version=d["version"], definition_hash=d["hash"], engine_version=CORE_VERSION,
        ))
    return result, evidence

