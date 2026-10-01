"""Safety-only port from HA 4905e35c weather_hazards.py (MIT).

No collectors or weather watch features. Keep original hazard semantics for parity.
This source file is part of every definition hash.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from .spatial import haversine_km

EXPOSURE_HOME = "home"          # at or beside the house; no travel


EXPOSURE_BEACH = "beach"        # on the sand or rocks, often at night


EXPOSURE_COASTAL = "coastal"    # bluffs, overlooks, boardwalks, piers


EXPOSURE_BOAT = "boat"          # on the water with an operator


EXPOSURE_MOUNTAIN = "mountain"  # Sierra roads and trails


EXPOSURE_DESERT = "desert"


EXPOSURE_GENERAL = "general"


_ALL = None


STATE_SAFE = "safe"


STATE_CAUTION = "caution"


STATE_UNSAFE = "unsafe"


STATE_UNKNOWN = "unknown"


_TRAVEL = frozenset({EXPOSURE_BEACH, EXPOSURE_COASTAL, EXPOSURE_BOAT, EXPOSURE_MOUNTAIN,
                     EXPOSURE_DESERT, EXPOSURE_GENERAL})


_SHORE = frozenset({EXPOSURE_BEACH, EXPOSURE_COASTAL})


HAZARDS: dict[str, tuple] = {
    # Life-threatening wherever you are: never send anyone into these.
    **{event: (_ALL, _ALL, "Do not go; this is not a storm-chasing system.") for event in (
        "Tornado Warning", "Severe Thunderstorm Warning", "Flash Flood Warning", "Flood Warning",
        "Winter Storm Warning", "Blizzard Warning", "Ice Storm Warning", "High Wind Warning",
        "Extreme Wind Warning", "Fire Warning", "Evacuation Immediate", "Dust Storm Warning",
        "Tsunami Warning", "Snow Squall Warning", "Civil Danger Warning", "Shelter In Place Warning",
        "Tropical Storm Warning", "Hurricane Warning", "Storm Surge Warning", "Hurricane Force Wind Warning")},
    # Heat: dangerous to be out in, not to glance at from the porch.
    "Excessive Heat Warning": (_TRAVEL, _ALL, "Dangerous heat; do not plan time outdoors away from shelter."),
    "Extreme Heat Warning": (_TRAVEL, _ALL, "Dangerous heat; do not plan time outdoors away from shelter."),
    "Avalanche Warning": (frozenset({EXPOSURE_MOUNTAIN}), _ALL, "Avalanche danger; stay off and below slopes."),
    # Water and shoreline.
    "Coastal Flood Warning": (_SHORE, _ALL, "Coastal flooding: stay off beaches, seawalls and low shore roads."),
    "High Surf Warning": (frozenset({EXPOSURE_BEACH}), frozenset({EXPOSURE_COASTAL, EXPOSURE_BOAT, EXPOSURE_HOME}),
                          "Photograph only from high, set-back ground - never on the beach, rocks or jetties."),
    "High Surf Advisory": ((), _SHORE | {EXPOSURE_BOAT},
                           "Large breaking waves: stay well above the wash line; never on rocks or jetties."),
    "Beach Hazards Statement": ((), _SHORE, "Sneaker waves and rip currents: stay above the wash line."),
    "Rip Current Statement": ((), _SHORE, "Rip currents: stay out of the water."),
    "Coastal Flood Advisory": ((), _SHORE, "Minor coastal flooding: low beaches and paths may be awash."),
    "Special Marine Warning": (frozenset({EXPOSURE_BOAT}), _SHORE, "Hazardous conditions on the water; trips will be cancelled."),
    "Gale Warning": (frozenset({EXPOSURE_BOAT}), (), "Gale on the water; no boat trip."),
    "Storm Warning": (frozenset({EXPOSURE_BOAT}), (), "Storm-force wind on the water; no boat trip."),
    "Small Craft Advisory": ((), frozenset({EXPOSURE_BOAT}), "Rough water; expect a hard ride or a cancelled trip."),
    # Fire weather is not a fire.
    "Red Flag Warning": ((), _TRAVEL, "Critical fire weather: no flame or sparks, don't park on dry grass, and check for new fires and closures."),
    "Fire Weather Watch": ((), _TRAVEL, "Fire weather possible; check for new fires and closures."),
    # Advisories and watches: tell the photographer, do not hide the row.
    **{event: ((), _ALL, note) for event, note in (
        ("Wind Advisory", "Strong gusts: secure the tripod; no drone."),
        ("Dense Fog Advisory", "Dense fog: slow, hazardous driving; the view may be gone."),
        ("Heat Advisory", "Heat: carry water; avoid midday exertion."),
        ("Winter Weather Advisory", "Snow or ice on the roads: carry chains; check road status."),
        ("Air Quality Alert", "Poor air quality."),
        ("Dense Smoke Advisory", "Dense smoke: poor air and visibility."),
        ("Flood Advisory", "Minor flooding: avoid low crossings."),
        ("Winter Storm Watch", "A winter storm is possible: recheck before leaving."),
        ("Flash Flood Watch", "Flash flooding possible: avoid washes and slot canyons."),
        ("Severe Thunderstorm Watch", "Severe storms possible: recheck before leaving."),
        ("Tornado Watch", "Tornadoes possible: recheck before leaving."),
        ("High Wind Watch", "High wind possible: recheck before leaving."),
        ("Tropical Storm Watch", "Tropical storm possible: recheck before leaving."),
        ("Hurricane Watch", "Hurricane possible: recheck before leaving."),
        ("Freeze Warning", "Below-freezing temperatures: dress for it; watch for ice."),
        ("Extreme Cold Warning", "Dangerous cold: dress for it; watch for ice."),
        ("Extreme Cold Watch", "Dangerous cold possible."),
    )},
}


COUNTY_POINTS = (
    (34.742, -120.572, "006083"), (34.389, -119.502, "006083"), (34.585, -119.980, "006083"),
    (34.418, -119.670, "006083"), (34.758, -120.643, "006083"),
    (35.131, -120.635, "006079"), (35.666, -121.257, "006079"), (35.191, -119.793, "006079"),
    (35.178, -120.740, "006079"),
    (34.249, -119.264, "006111"), (34.725, -118.400, "006037"),
    (36.372, -121.902, "006053"), (36.605, -121.890, "006053"), (36.491, -121.183, "006069"),
    (36.565, -118.773, "006107"), (35.924, -118.585, "006107"), (36.788, -118.669, "006019"),
    (37.172, -122.222, "006087"), (36.505, -117.079, "006027"), (37.361, -118.400, "006027"),
    (37.227, -118.626, "006027"), (37.746, -119.594, "006043"), (37.783, -119.080, "006051"),
    (37.950, -119.220, "006051"), (37.630, -119.085, "006051"), (39.097, -120.032, "006017"),
    (38.750, -119.950, "006003"), (37.180, -120.600, "006047"), (38.156, -121.416, "006077"),
    (33.256, -116.375, "006073"), (32.860, -117.250, "006073"), (38.100, -122.950, "006041"),
    (39.421, -122.165, "006021"), (33.873, -115.901, "006065"),
)


COUNTY_MATCH_KM = 40.0


@dataclass(frozen=True)
class AlertCheck:
    """What the alert feed can currently say, and whether it can say "nothing".

    ``complete`` is False when the latest fetch failed or carried unusable
    features. The alerts that were readable still count - an unsafe match
    still blocks - but an empty match is no longer "safe".
    """

    alerts: tuple = ()
    complete: bool = True
    checked_at: datetime | None = None
    problem: str = ""
    issues: tuple = field(default_factory=tuple)


def county_for(latitude: float, longitude: float) -> str | None:
    best = min(COUNTY_POINTS, key=lambda row: haversine_km(latitude, longitude, row[0], row[1]))
    return best[2] if haversine_km(latitude, longitude, best[0], best[1]) <= COUNTY_MATCH_KM else None


def _in_ring(point, ring) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def in_geometry(latitude: float, longitude: float, geometry: dict) -> bool:
    """Point in a GeoJSON Polygon/MultiPolygon (outer rings, lon-lat order)."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    point = (longitude, latitude)
    for polygon in polygons:
        try:
            ring = [tuple(map(float, pair[:2])) for pair in polygon[0]]
        except (TypeError, ValueError, IndexError):
            continue
        if len(ring) >= 3 and _in_ring(point, ring):
            return True
    return False


def _time(value) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def alerts_at(alerts: list, latitude: float, longitude: float, start: datetime, end: datetime,
              now: datetime) -> tuple[list[dict], bool]:
    """Active alerts overlapping a place and time, and whether the place was checkable.

    Checkable means the place resolves to an alert county: only then does an
    empty result mean "no alerts here". A polygon from some other alert does
    not make an unlisted place checkable - county-only alerts would be missed.
    """
    county = county_for(latitude, longitude)
    found = []
    for alert in alerts or []:
        expires = _time(alert.get("ends")) or _time(alert.get("expires"))
        onset = _time(alert.get("onset"))
        if expires and (expires <= now or expires < start):
            continue
        if onset and onset > end:
            continue
        geometry = alert.get("geometry")
        if geometry:
            hit = in_geometry(latitude, longitude, geometry)
        else:
            hit = bool(county and county in (alert.get("same") or []))
        if hit:
            found.append(alert)
    return found, county is not None


def _rule(alert: dict) -> tuple:
    """The (unsafe, caution, note) rule for an alert, including unknown events."""
    event = alert.get("event", "")
    if event in HAZARDS:
        return HAZARDS[event]
    # An event this table has not reviewed: trust NWS's own severity.
    if (alert.get("severity") or "") in ("Extreme", "Severe"):
        return _ALL, _ALL, "Do not go until you have read it."
    return (), _ALL, ""


def _applies(exposures, exposure: str) -> bool:
    return exposures is _ALL or exposure in exposures


MARINE_UNCHECKED = ("Marine conditions not checked: NWS coastal-waters (marine zone) warnings are not "
                    "connected, so a clear land check says nothing about the sea. Held until marine coverage "
                    "exists; check the coastal waters forecast and the operator.")


def _as_check(alerts) -> AlertCheck | None:
    if alerts is None or isinstance(alerts, AlertCheck):
        return alerts
    return AlertCheck(alerts=tuple(alerts or ()), complete=True)


def safety(item, alerts, now: datetime, exposure: str = EXPOSURE_GENERAL) -> dict:
    """SAFE, CAUTION, UNSAFE or UNKNOWN for one opportunity, and what to say.

    ``alerts`` is an ``AlertCheck``, a plain list (a complete check), or None
    when the feed failed or is stale: that is UNKNOWN, never SAFE. An
    incomplete check still lets a matching warning block, but cannot conclude
    safe or merely-cautious. ``travel`` says whether going there means leaving
    home; the eligibility gate holds a travel row whose safety is unknown.

    ``components`` keeps land and marine apart. For a boat the marine
    component is unknown (see module docstring), so the overall state is at
    best unknown.
    """
    boat = exposure == EXPOSURE_BOAT
    # Every boat trip means leaving home, whatever the drive to the harbour.
    travel = boat or (exposure != EXPOSURE_HOME and (getattr(item, "drive_hours", None) or 0) > 0.25)
    marine = STATE_UNKNOWN if boat else None
    check = _as_check(alerts)
    base = {"unsafe": False, "notes": [MARINE_UNCHECKED] if boat else [], "checked": False, "travel": travel,
            "state": STATE_UNKNOWN, "components": {"land": STATE_UNKNOWN, "marine": marine}}
    if check is None:
        return {**base, "summary": "Safety not checked: NWS alerts are unavailable. Check warnings before leaving."}
    if item.latitude is None or item.longitude is None:
        return {**base, "summary": "Safety not checked: this location cannot be matched to NWS alerts."}
    end = item.end or item.start + timedelta(hours=2)
    active, checkable = alerts_at(list(check.alerts), item.latitude, item.longitude, item.start, end, now)
    notes, unsafe, caution = [], False, False
    for alert in active:
        event = alert.get("event", "")
        blocks, warns, note = _rule(alert)
        if _applies(blocks, exposure):
            unsafe = True
            notes.insert(0, f"{event} in effect. {note}".strip())
        elif _applies(warns, exposure):
            caution = True
            notes.append(f"{event} in effect. {note}".strip())
    if unsafe:
        land, summary = STATE_UNSAFE, "Unsafe: " + notes[0]
    elif not check.complete:
        land = STATE_UNKNOWN
        summary = ("Safety not fully checked: the NWS alert feed was incomplete"
                   + (f" ({check.problem})" if check.problem else "") + ". Check warnings before leaving.")
    elif caution:
        land, summary = STATE_CAUTION, "Caution: " + "; ".join(note for note in notes if " in effect" in note)
    elif checkable:
        land, summary = STATE_SAFE, "No NWS warnings for this place and time."
    else:
        land, summary = STATE_UNKNOWN, "Safety not checked: this location is not matched to an NWS county. Check warnings yourself."
    state = land
    if boat and land != STATE_UNSAFE:
        # Land may be clear; the sea is unassessed. Unknown, and say why.
        state = STATE_UNKNOWN
        summary = MARINE_UNCHECKED if land in (STATE_SAFE, STATE_CAUTION) else summary + " " + MARINE_UNCHECKED
    if boat:
        notes.append(MARINE_UNCHECKED)
    return {"unsafe": unsafe, "notes": notes, "checked": (checkable and check.complete) or unsafe,
            "travel": travel, "state": state, "summary": summary,
            "components": {"land": land, "marine": marine}}
