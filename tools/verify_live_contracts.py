"""Explicit manual smoke probe: <=3 iNat, <=4 WFIGS, <=3 NWS HTTP requests.

No database mutation, no coordinates/payload dump, never executed by standard CI.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from pec.sources.contracts import CONTRACTS, INATURALIST, WFIGS, NWS
from pec.sources.fetch import query
from pec.sources.http import Client, FetchError
from pec.sources import inaturalist, wfigs, nws


async def main(source, bounded_poll=False):
    contract = CONTRACTS[source]
    client = Client(
        contract,
        "PhotographyEventsCore-manual-contract-verification (+https://github.com/Tmatz27/photography-events-core)",
    )
    report = dict(
        source=source,
        contract_version=contract.version,
        verified_at=datetime.now(UTC).isoformat(),
        scope="Few-request schema sample; not a daily volume estimate or production qualification",
    )
    if bounded_poll:
        from pec.sources.fetch import fetch
        import time

        start = time.monotonic()
        batch = await fetch(contract, client, datetime.now(UTC), max_pages=2)
        report.update(
            status="passed" if batch.complete and not batch.rejected else "incomplete",
            scope="Bounded initial live query (iNat trailing 14 days; current fire/weather); <=2 result pages, no DB mutation; not a daily volume estimate",
            received=batch.received,
            accepted=len(batch.records),
            rejected=len(batch.rejected),
            unique_records=len({r.external_id for r in batch.records}),
            obscured=sum(r.spatial_basis == "obscured_cell" for r in batch.records),
            private=sum(r.spatial_basis == "private_unavailable" for r in batch.records),
            parser_errors=sorted({code for _, code in batch.rejected}),
            error_code=batch.failure_code,
            requests=client.requests,
            bytes_received=client.bytes_received,
            rate_limit_count=client.rate_limited,
            poll_seconds=round(time.monotonic() - start, 3),
        )
        print(json.dumps(report, sort_keys=True))
        return
    try:
        if contract == INATURALIST:
            body = await client.get(
                query(
                    contract.interface,
                    taxon_id="41638,48662",
                    per_page=2,
                    swlng=-121.3,
                    swlat=34.2,
                    nelng=-119.0,
                    nelat=36.2,
                    order_by="id",
                    order="desc",
                )
            )
            values = body["results"]
            ids = ",".join(str(v["id"]) for v in values)
            if ids:
                refresh = await client.get(query(contract.interface, id=ids, per_page=200))
                if {r["id"] for r in refresh["results"]} != {r["id"] for r in values}:
                    raise FetchError("identity_refresh_contract_drift")
            facts = [inaturalist.parse(v) for v in values]
            report.update(
                received=len(values),
                accepted=len(facts),
                uuid_present=all(v.get("uuid") for v in values),
                obscured=sum(f.spatial_basis == "obscured_cell" for f in facts),
                private=sum(f.spatial_basis == "private_unavailable" for f in facts),
            )
        elif contract == WFIGS:
            meta = await client.get(query(contract.interface, f="json"))
            fields = {f["name"] for f in meta["fields"]}
            if not set(wfigs.FIELDS) <= fields or meta["geometryType"] != "esriGeometryPolygon":
                raise FetchError("perimeter_schema_drift")
            body = await client.get(
                query(
                    contract.interface + "/query",
                    f="geojson",
                    where="1=1",
                    resultRecordCount=1,
                    outFields=",".join(wfigs.FIELDS),
                    returnGeometry="true",
                    outSR=4326,
                )
            )
            facts = [wfigs.parse(v) for v in body["features"]]
            report.update(
                received=len(facts),
                accepted=len(facts),
                max_record_count=meta["maxRecordCount"],
                fire_types=sorted({f.metadata["fire_type"] for f in facts}),
            )
        elif contract == NWS:
            body = await client.get("https://api.weather.gov/alerts/active?point=35.1307,-120.6349")
            facts = [nws.alert(v) for v in body["features"]]
            point = await client.get("https://api.weather.gov/points/35.1307,-120.6349")
            forecast = await client.get(point["properties"]["forecastHourly"])
            from pec.sources.models import timestamp

            updated = timestamp(forecast["properties"]["updateTime"])
            facts.extend(nws.forecast(v, updated) for v in forecast["properties"]["periods"][:2])
            report.update(received=len(facts), accepted=len(facts), provider_updated_at=updated.isoformat())
        report["status"] = "passed"
    except (FetchError, KeyError, TypeError, ValueError) as exc:
        report.update(status="not_verified", code=getattr(exc, "code", "schema_drift"))
    report.update(
        requests=client.requests, bytes_received=client.bytes_received, rate_limit_count=client.rate_limited
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=tuple(CONTRACTS), required=True)
    parser.add_argument(
        "--bounded-poll",
        action="store_true",
        help="Read the actual bounded initial scope (two pages maximum)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.source, args.bounded_poll))
