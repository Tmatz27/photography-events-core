"""Complete bounded pagination; a page/budget failure is never a successful empty feed."""

import json
from datetime import timedelta
from urllib.parse import urlencode

from . import inaturalist, nws, wfigs
from .contracts import BOUNDS, INATURALIST, NWS, PISMO, TAXA, WFIGS
from .http import FetchError
from .models import Batch, RecordError, timestamp


def query(base, **params):
    return base + "?" + urlencode(params)


def observation_params(now, cursor=None):
    params = dict(
        taxon_id=",".join(map(str, TAXA)),
        per_page=200,
        order_by="id",
        order="asc",
        swlng=BOUNDS[0],
        swlat=BOUNDS[1],
        nelng=BOUNDS[2],
        nelat=BOUNDS[3],
        d1=(now - timedelta(days=14)).date().isoformat(),
    )
    if cursor:
        params["updated_since"] = (cursor - timedelta(minutes=5)).isoformat()
    return params


async def observations(client, batch, now, cursor, known, max_pages):
    params = observation_params(now, cursor)
    last = 0
    seen = set()
    for page in range(max_pages):
        body = await client.get(
            query(INATURALIST.interface, **params, **({"id_above": last} if last else {}))
        )
        values = body.get("results")
        if (
            not isinstance(values, list)
            or type(body.get("total_results")) is not int
            or body["total_results"] < 0
        ):
            raise FetchError("invalid_observation_page")
        if not values:
            if page == 0 and body["total_results"] > 0:
                raise FetchError("empty_nonempty_observation_page")
            break
        ids = [r.get("id") for r in values if isinstance(r, dict)]
        batch.parse(values, inaturalist.parse)
        ids = [i for i in ids if type(i) is int and i > 0]
        if not ids or any(type(i) is not int or i <= last for i in ids) or ids != sorted(set(ids)):
            raise FetchError("observation_pagination_drift")
        seen.update(ids)
        last = ids[-1]
        if len(values) < 200:
            break
    else:
        raise FetchError("observation_page_budget")
    # ID-list search is deliberately outside the spatial/taxon/date search so
    # a correction moving a known record away does not preserve its old point.
    if known:
        ids = sorted(known)
        body = await client.get(
            query(INATURALIST.interface, id=",".join(map(str, ids)), per_page=200, order_by="id", order="asc")
        )
        values = body.get("results")
        if (
            not isinstance(values, list)
            or type(body.get("total_results")) is not int
            or body["total_results"] != len(values)
            or len(values) > 200
        ):
            raise FetchError("incomplete_identity_refresh")
        returned = {r.get("id") for r in values if isinstance(r, dict)}
        if not returned <= set(ids) or len(returned) != len(values):
            raise FetchError("invalid_identity_refresh")
        batch.parse([r for r in values if r["id"] not in seen], inaturalist.parse)
        batch.unavailable_ids.update(known[i] for i in ids if i not in returned)


async def fires(client, batch, now, max_pages):
    base = WFIGS.interface
    meta = await client.get(query(base, f="json"))
    fields = {f.get("name") for f in meta.get("fields", []) if isinstance(f, dict)}
    if (
        meta.get("geometryType") != "esriGeometryPolygon"
        or not set(wfigs.FIELDS) <= fields
        or not isinstance(meta.get("maxRecordCount"), int)
    ):
        raise FetchError("perimeter_schema_drift")
    native = meta.get("editingInfo", {}).get("dataLastEditDate")
    batch.provider_updated_at = wfigs.epoch(native)
    envelope = json.dumps(
        dict(xmin=BOUNDS[0], ymin=BOUNDS[1], xmax=BOUNDS[2], ymax=BOUNDS[3], spatialReference={"wkid": 4326})
    )
    id_body = await client.get(
        query(
            base + "/query",
            f="json",
            where="1=1",
            returnIdsOnly="true",
            geometry=envelope,
            geometryType="esriGeometryEnvelope",
            inSR=4326,
            spatialRel="esriSpatialRelIntersects",
        )
    )
    ids = id_body.get("objectIds")
    if ids is None and id_body.get("objectIdFieldName") == "OBJECTID":
        ids = []
    if (
        not isinstance(ids, list)
        or any(type(i) is not int or i <= 0 for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise FetchError("invalid_perimeter_ids")
    size = min(2000, meta["maxRecordCount"])
    if size <= 0 or len(ids) > size * max_pages:
        raise FetchError("perimeter_page_budget")
    ids = sorted(ids)
    for offset in range(0, len(ids), size):
        wanted = ids[offset : offset + size]
        body = await client.get(
            query(
                base + "/query",
                f="geojson",
                objectIds=",".join(map(str, wanted)),
                outFields=",".join(wfigs.FIELDS),
                outSR=4326,
                returnGeometry="true",
            )
        )
        features = body.get("features")
        if isinstance(features, list):
            batch.parse(features, wfigs.parse)
        if (
            not isinstance(features, list)
            or body.get("exceededTransferLimit")
            or (body.get("properties") or {}).get("exceededTransferLimit")
            or {f.get("properties", {}).get("OBJECTID") for f in features if isinstance(f, dict)}
            != set(wanted)
            or len(features) != len(wanted)
        ):
            raise FetchError("incomplete_perimeter_page")
    after = await client.get(query(base, f="json"))
    if after.get("editingInfo", {}).get("dataLastEditDate") != native:
        raise FetchError("perimeter_snapshot_changed")
    batch.snapshot = True
    batch.records = wfigs.combine(batch.records, batch.rejected)


async def weather(client, batch, now, max_pages):
    base = "https://api.weather.gov"
    # /alerts/active does not accept Limit in the official OpenAPI contract.
    url = query(base + "/alerts/active", point=f"{PISMO['latitude']},{PISMO['longitude']}")
    visited = set()
    alert_asof = None
    for _ in range(max_pages):
        if url in visited:
            raise FetchError("alert_pagination_cycle")
        visited.add(url)
        body = await client.get(url)
        if body.get("type") != "FeatureCollection" or not isinstance(body.get("features"), list):
            raise FetchError("invalid_alert_collection")
        # Native collection update, not response Date/fetched_at, supplies age.
        if body.get("updated"):
            alert_asof = timestamp(body["updated"])
        batch.parse(body["features"], nws.alert)
        url = (body.get("pagination") or {}).get("next")
        if not url:
            break
    else:
        raise FetchError("alert_page_budget")
    point_info = await client.get(base + f"/points/{PISMO['latitude']},{PISMO['longitude']}")
    forecast_url = point_info.get("properties", {}).get("forecastHourly")
    if not isinstance(forecast_url, str):
        raise FetchError("forecast_point_schema_drift")
    body = await client.get(forecast_url)
    props = body.get("properties")
    if not isinstance(props, dict) or not isinstance(props.get("periods"), list):
        raise FetchError("forecast_schema_drift")
    updated = timestamp(props.get("updateTime"), "missing_forecast_native_time")
    batch.parse(props["periods"], lambda p: nws.forecast(p, updated))
    # Forecast is independent CONDITION; alert freshness is retained separately.
    batch.provider_updated_at = updated
    batch.snapshot = True
    batch.alert_asof = alert_asof


async def fetch(contract, client, now, *, cursor=None, known=None, max_pages=20):
    batch = Batch()
    try:
        if contract.source_key == INATURALIST.source_key:
            await observations(client, batch, now, cursor, known or {}, max_pages)
        elif contract.source_key == WFIGS.source_key:
            await fires(client, batch, now, max_pages)
        elif contract.source_key == NWS.source_key:
            await weather(client, batch, now, max_pages)
        else:
            raise FetchError("unknown_source_contract")
    except (FetchError, RecordError) as exc:
        batch.complete = False
        batch.http_status = getattr(exc, "status", 502)
        batch.retry_after = getattr(exc, "retry_after", None)
        batch.failure_code = exc.code
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        batch.complete = False
        batch.http_status = 502
        batch.failure_code = "collection_schema_drift"
    batch.requests = client.requests
    batch.bytes_received = client.bytes_received
    batch.rate_limited = client.rate_limited
    if batch.provider_updated_at is None and batch.records:
        batch.provider_updated_at = max(r.provider_updated_at for r in batch.records)
    return batch
