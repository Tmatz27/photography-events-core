"""Explicit collection sites, not a six-hour travel classifier."""

import copy
import json
import re

PARKS = ("yose", "seki", "deva", "jotr", "chis", "pinn", "redw", "lavo")
# seki is the official shared Sequoia AND Kings Canyon park code.
DEFAULT = {
    "usgs_water": ["USGS-11109000", "USGS-11264500", "USGS-11266500"],
    "cdec_river": ["POH"],
    "cdec_rainfall": ["GIN"],
    "cdec_snow": ["GIN"],
    "nwps": ["POHC1"],
    "nps": list(PARKS),
    "history_start": "2026-01-01",
    "history_end": "recent",
}


def scope(value=None):
    result = copy.deepcopy(DEFAULT)
    if value is not None:
        values = json.loads(value) if isinstance(value, str) else value
        if not isinstance(values, dict) or set(values) - set(DEFAULT):
            raise ValueError("Unknown collection scope fields")
        result.update(values)
    patterns = {
        "usgs_water": r"USGS-[0-9]{8,15}",
        "nwps": r"[A-Z0-9]{5}",
        "nps": r"[a-z]{4}",
        **{k: r"[A-Z0-9]{3}" for k in DEFAULT if k.startswith("cdec_")},
    }
    for key, pattern in patterns.items():
        ids = result[key]
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= (8 if key == "usgs_water" else 12)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Collection scope requires 1–12 distinct approved station/park IDs")
        if any(not isinstance(v, str) or re.fullmatch(pattern, v) is None for v in ids):
            raise ValueError("Invalid collection station/park identity")
    if not set(PARKS) <= set(result["nps"]):
        raise ValueError("NPS scope must retain all nine California national parks")
    from datetime import date

    start = date.fromisoformat(result["history_start"])
    end = date.today() if result["history_end"] == "recent" else date.fromisoformat(result["history_end"])
    if end <= start or (end - start).days > 3660:
        raise ValueError("History must be a finite interval of at most ten years")
    return result
