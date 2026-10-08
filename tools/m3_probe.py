"""Manual bounded public-contract inspection; not imported by CI."""

import json
import time
import urllib.request
from pathlib import Path

from pec.sources import inaturalist, wfigs
from pec.sources.contracts import INATURALIST, WFIGS

OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/providers"


def get(url):
    time.sleep(1.1)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PhotographyEventsCore-M3A-contract-verification (+https://github.com/Tmatz27/photography-events-core)"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for tid in (41638, 48662):
        body = get(f"https://api.inaturalist.org/v1/taxa/{tid}")
        print("taxon", tid, [(t["id"], t["name"]) for t in body["results"]])
    body = get(
        INATURALIST.interface
        + "?taxon_id=41638,48662&per_page=2&order_by=id&order=desc&swlng=-121.3&swlat=34.2&nelng=-119.0&nelat=36.2"
    )
    print(
        "inaturalist",
        {
            "total_results": body.get("total_results"),
            "sample": len(body.get("results", [])),
            "uuid_present": all(r.get("uuid") for r in body.get("results", [])),
        },
    )
    clean = []
    for r in body.get("results", []):
        try:
            fact = inaturalist.parse(r)
            # Deliberately fictional identifiers/point/prose; provider field topology retained.
            p = fact.payload
            p.update(
                uuid=f"00000000-0000-4000-8000-{len(clean) + 1:012d}",
                id=len(clean) + 1,
                description="Sanitized provider response",
            )
            if p.get("geojson"):
                p["geojson"] = {"type": "Point", "coordinates": [-120.63, 35.13]}
            clean.append(p)
        except ValueError as exc:
            print("inaturalist_rejection", str(exc))
    (OUT / "inaturalist.json").write_text(json.dumps({"results": clean}, indent=2) + "\n", encoding="utf-8")
    meta = get(WFIGS.interface + "?f=json")
    print("wfigs", {"geometryType": meta.get("geometryType"), "maxRecordCount": meta.get("maxRecordCount")})
    for f in meta.get("fields", []):
        if f["name"] in (
            "poly_FeatureCategory",
            "poly_FeatureStatus",
            "poly_FeatureAccess",
            "poly_IsVisible",
            "poly_DeleteThis",
            "attr_IncidentTypeCategory",
        ):
            print("enum", f["name"], f.get("domain"))
    body = get(
        WFIGS.interface
        + "/query?f=geojson&where=1%3D1&resultRecordCount=1&outFields="
        + ",".join(wfigs.FIELDS)
        + "&outSR=4326"
    )
    features = body.get("features", [])
    print(
        "wfigs_sample",
        [
            dict(
                (k, r["properties"].get(k))
                for k in (
                    "poly_FeatureCategory",
                    "poly_FeatureStatus",
                    "poly_FeatureAccess",
                    "poly_IsVisible",
                    "poly_DeleteThis",
                    "attr_IncidentTypeCategory",
                    "attr_ActiveFireCandidate",
                )
            )
            for r in features
        ],
    )
    for r in features:
        r["id"] = 1
        r["properties"].update(
            OBJECTID=1,
            GlobalID="{00000000-0000-4000-8000-000000000001}",
            poly_IRWINID="{00000000-0000-4000-8000-000000000002}",
        )
        r["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-120.636, 35.13],
                    [-120.633, 35.13],
                    [-120.633, 35.132],
                    [-120.636, 35.132],
                    [-120.636, 35.13],
                ]
            ],
        }
    (OUT / "wfigs.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
