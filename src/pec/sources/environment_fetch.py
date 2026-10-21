"""Bounded live and independent history slices; never manufacture an empty success."""

from datetime import timedelta
from urllib.parse import urlencode, urlparse, parse_qs

from .environment_contracts import ENVIRONMENT_CONTRACTS, base_key, request_budget
from .environment_scope import scope
from . import environment_models as models
from . import environment_health as health
from .http import FetchError
from .models import RecordError, timestamp
from ..ingestion import fingerprint


def query(base, **params):
    return base + "?" + urlencode(params)


def window(key, options, checkpoint, now, cursor, history):
    if not history:
        frontier = (
            timestamp(checkpoint["incremental_end"])
            if checkpoint.get("incremental_end")
            else now - timedelta(hours=6)
        )
        start = frontier - timedelta(hours=1) if checkpoint.get("incremental_end") else frontier
        end = min(now, start + timedelta(days=1))
        return start, end, {"incremental_end": end.isoformat()}
    # A bounded DAY for ONE station is independently checkpointed; history
    # progress never advances the incremental cursor or consumes its lease.
    station_index = checkpoint.get("station_index", 0)
    if type(station_index) is not int or not 0 <= station_index < len(options[key]):
        raise FetchError("invalid_history_checkpoint")
    start = timestamp(checkpoint.get("next_start", options["history_start"] + "T00:00:00Z"))
    if key == "nwps" and not checkpoint.get("next_start"):
        # NWPS supplies a rolling observed series, not an arbitrary archive API.
        start = max(start, now - timedelta(days=29))
    end = now - timedelta(hours=6)
    if options["history_end"] != "recent":
        end = min(timestamp(options["history_end"] + "T00:00:00Z"), end)
    if start >= end:
        return (
            start,
            start,
            {"complete": True, "next_start": start.isoformat(), "station_index": station_index},
        )
    stop = (
        timestamp(checkpoint["window_end"])
        if checkpoint.get("window_end")
        else min(start + timedelta(days=1), end)
    )
    next_station = (station_index + 1) % len(options[key])
    return (
        start,
        stop,
        {
            "next_start": (stop if next_station == 0 else start).isoformat(),
            "station_index": next_station,
            "complete": False,
            "window_end": stop.isoformat() if next_station else None,
        },
    )


async def usgs(client, batch, stations, start, end, max_pages):
    budget = max_pages
    for station in stations:
        # One explicit parameter per query avoids reliance on undocumented OR syntax.
        for parameter in models.USGS_PARAMETERS:
            url = query(
                ENVIRONMENT_CONTRACTS["usgs_water"].interface,
                f="json",
                monitoring_location_id=station,
                parameter_code=parameter,
                datetime=start.isoformat() + "/" + end.isoformat(),
                limit=1000,
            )
            seen_urls, seen_ids = set(), set()
            while url:
                if budget <= 0 or url in seen_urls:
                    raise FetchError("usgs_pagination_budget_or_cycle")
                # A next link must retain this exact station, parameter and window.
                params = parse_qs(urlparse(url).query)
                if (
                    urlparse(url).path != "/ogcapi/v1/collections/continuous/items"
                    or params.get("monitoring_location_id") != [station]
                    or params.get("parameter_code") != [parameter]
                    or params.get("datetime") != [start.isoformat() + "/" + end.isoformat()]
                ):
                    raise FetchError("usgs_pagination_scope_drift")
                seen_urls.add(url)
                body = await client.get(url)
                budget -= 1
                values = body.get("features")
                if (
                    body.get("type") != "FeatureCollection"
                    or not isinstance(values, list)
                    or body.get("numberReturned") != len(values)
                ):
                    raise FetchError("invalid_usgs_collection")

                def parse_feature(feature):
                    p = feature.get("properties", {})
                    if p.get("monitoring_location_id") != station or p.get("parameter_code") != parameter:
                        raise RecordError("usgs_record_scope_drift")
                    valid = timestamp(p.get("time"))
                    if not start <= valid <= end or feature.get("id") in seen_ids:
                        raise RecordError("usgs_record_window_or_duplicate")
                    seen_ids.add(feature.get("id"))
                    return models.usgs(feature)

                batch.parse(values, parse_feature)
                links = [v.get("href") for v in body.get("links", []) if v.get("rel") == "next"]
                if len(links) > 1 or (links and not values):
                    raise FetchError("invalid_usgs_next_link")
                url = links[0] if links else None


async def cdec(client, batch, key, stations, start, end, *, history=False):
    for station in stations:
        sensors = models.CDEC_PARAMETERS[key]
        duration = "E" if key == "cdec_river" else "D"
        body = await client.get(
            query(
                ENVIRONMENT_CONTRACTS[key].interface,
                Stations=station,
                SensorNums=",".join(map(str, sensors)),
                dur_code=duration,
                Start=(start - timedelta(days=2) if duration == "D" else start)
                .astimezone(models.PST)
                .strftime("%Y-%m-%dT%H:%M"),
                End=end.astimezone(models.PST).strftime("%Y-%m-%dT%H:%M"),
            ),
            allow_list=True,
        )
        if not isinstance(body, list) or len(body) > 2000:
            raise FetchError("invalid_cdec_page")
        seen = set()

        def parse_row(row):
            if (
                row.get("stationId") != station
                or row.get("SENSOR_NUM") not in sensors
                or row.get("durCode") != duration
            ):
                raise RecordError("cdec_scope_drift")
            identity = (row.get("SENSOR_NUM"), row.get("date"))
            if identity in seen:
                raise RecordError("cdec_duplicate_record")
            seen.add(identity)
            return models.cdec(row, key)

        for row in body:
            before = len(batch.records)
            batch.parse([row], parse_row)
            if len(batch.records) > before:
                fact = batch.records[-1]
                if fact.valid_at > end or ((duration == "E" or history) and fact.valid_at < start):
                    batch.records.pop()
                    batch.skipped.append((None, "outside_requested_interval"))
        # A bounded, fully decoded [] is a completed empty window, not HTTP 502.
        # Rejected rows remain incomplete; neither an error nor absence deletes data.


async def nwps(client, batch, stations, start, end, *, history=False):
    for station in stations:
        base = ENVIRONMENT_CONTRACTS["nwps"].interface + "/gauges/" + station
        meta = await client.get(base)
        if meta.get("lid") != station:
            raise FetchError("nwps_station_mismatch")
        geometry = {"type": "Point", "coordinates": [meta["longitude"], meta["latitude"]]}
        # Retain flood thresholds and original gauge attribution as reference
        # evidence. Thresholds are NOT forecast values or inferred road closures.
        batch.received += 1
        batch.records.append(
            models.make(
                "nwps",
                station + ":metadata",
                station,
                "gauge_metadata",
                meta,
                kind="reference",
                geometry=geometry,
                metadata={
                    "usgs_id": meta.get("usgsId"),
                    "reference_content": {
                        k: meta[k]
                        for k in ("lid", "usgsId", "name", "flood", "datums", "dataAttribution")
                        if k in meta
                    },
                },
            )
        )
        body = await client.get(base + "/stageflow")
        if set(body) != {"observed", "forecast"}:
            raise FetchError("invalid_nwps_products")
        for product, section in body.items():
            if history and product == "forecast":
                continue
            if (
                not isinstance(section, dict)
                or not isinstance(section.get("data"), list)
                or len(section["data"]) > 6000
            ):
                raise FetchError("invalid_nwps_series")
            seen = set()

            def validate_row(row, dimension):
                if row.get("validTime") in seen:
                    raise RecordError("nwps_duplicate_valid_time")
                return models.nwps(row, section, product, station, dimension, geometry)

            for row in section["data"]:
                for dimension in ("primary", "secondary"):
                    if section.get(dimension + "Name"):
                        before = len(batch.records)
                        batch.parse([row], lambda r: validate_row(r, dimension))
                        if len(batch.records) > before:
                            fact = batch.records[-1]
                            # The returned observed series can reveal a stale last
                            # measurement outside this persistence window. Record
                            # its native time without repeatedly storing the series.
                            if not history:
                                health.note_fact(batch.environment["stations"][-1], fact)
                            if product == "observed" and not start <= fact.valid_at <= end:
                                batch.records.pop()
                                batch.skipped.append((None, "outside_requested_interval"))
                if isinstance(row, dict):
                    seen.add(row.get("validTime"))


async def nps(client, batch, parks, max_pages, now, checkpoint):
    key = getattr(client, "provider_secrets", {}).get("CORE_NPS_API_KEY")
    if not key:
        raise FetchError("credentials_needed", 401)
    checked = timestamp(checkpoint["parks_checked_at"]) if checkpoint.get("parks_checked_at") else None
    refresh = checked is None or now - checked >= timedelta(days=7) or checked > now
    for endpoint in ("alerts", "parks") if refresh else ("alerts",):
        start, total, identities = 0, None, set()
        for _ in range(max_pages):
            body = await client.get(
                query(
                    ENVIRONMENT_CONTRACTS["nps"].interface + "/" + endpoint,
                    parkCode=",".join(parks),
                    limit=50,
                    start=start,
                ),
                headers={"X-Api-Key": key},
            )
            values = body.get("data")
            try:
                count, offset, limit = int(body["total"]), int(body["start"]), int(body["limit"])
            except (ValueError, KeyError, TypeError):
                raise FetchError("invalid_nps_pagination") from None
            if (
                not isinstance(values, list)
                or count < 0
                or offset != start
                or limit != 50
                or (total is not None and total != count)
                or len(values) > limit
            ):
                raise FetchError("nps_pagination_drift")
            total = count

            def parse_row(row):
                identity = row.get("id")
                if row.get("parkCode") not in parks or not identity or identity in identities:
                    raise RecordError("nps_identity_or_scope_drift")
                identities.add(identity)
                return models.nps(row, endpoint)

            batch.parse(values, parse_row)
            start += len(values)
            if start == total:
                break
            if not values or start > total:
                raise FetchError("nps_incomplete_page")
        else:
            raise FetchError("nps_page_budget")
        if endpoint == "parks" and {
            r.station_id for r in batch.records if r.quantity == "park_information"
        } != set(parks):
            raise FetchError("nps_missing_park_information")
        # Explicit endpoint membership, including an actually empty alerts list.
        batch.records.append(
            models.make(
                "nps",
                "membership:" + endpoint,
                "california_parks",
                endpoint + "_snapshot",
                {"endpoint": endpoint, "native_ids": sorted(identities), "parks": parks},
                kind="reference",
                metadata={
                    "snapshot_complete": not batch.rejected,
                    "collection_membership": True,
                    "absence_means": "not in this endpoint snapshot, not proven deletion",
                    "native_ids": sorted(identities),
                    "parks": parks,
                },
            )
        )
    return (now if refresh else checked).isoformat()


async def collect_environment(contract, client, batch, now, cursor, checkpoint, max_pages):
    key = base_key(contract.source_key)
    if key not in ENVIRONMENT_CONTRACTS:
        raise FetchError("unknown_source_contract")
    options = scope(getattr(client, "collection_scope", None))
    client.request_limit = request_budget(contract, getattr(client, "collection_scope", None))
    client.preserve_numbers = True
    scope_hash = fingerprint(options)
    if checkpoint.get("scope_hash") != scope_hash:
        checkpoint = {}
    history = contract.source_key.endswith("_history")
    start, end, progress = window(key, options, checkpoint, now, cursor, history)
    stations = options[key]
    if history:
        if key not in ("usgs_water", "cdec_river", "cdec_rainfall", "cdec_snow", "nwps"):
            raise FetchError("provider_has_no_history_interface")
        if start == end:
            batch.checkpoint = {**progress, "scope_hash": scope_hash}
            return
        stations = [stations[checkpoint.get("station_index", 0)]]
    if key != "nps":
        batch.environment = dict(dataset=key, mode="historical" if history else "current", stations=[])
        for station in stations:
            outcome = health.start_station(batch, station, start, end)
            records, rejected, received, requests = (
                len(batch.records),
                len(batch.rejected),
                batch.received,
                client.requests,
            )
            successes = client.successful_requests
            error = None
            stop = batch.http_status == 429 or batch.retry_after is not None or batch.failure_code in (
                "untrusted_pagination_url",
                "usgs_pagination_scope_drift",
            )
            if stop:
                health.finish_station(
                    outcome, batch, records, rejected, received, 0, "not_requested_after_provider_failure"
                )
                continue
            try:
                if key == "usgs_water":
                    await usgs(client, batch, [station], start, end, max_pages)
                elif key.startswith("cdec_"):
                    await cdec(client, batch, key, [station], start, end, history=history)
                else:
                    await nwps(client, batch, [station], start, end, history=history)
            except (
                FetchError,
                RecordError,
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
                OverflowError,
            ) as exc:
                error = getattr(exc, "code", "station_schema_drift")
                batch.complete = False
                # Retain real provider status and Retry-After even if a sibling
                # succeeds; cancellation propagates to the ownership boundary.
                if batch.failure_code is None or getattr(exc, "retry_after", None):
                    batch.failure_code = error
                    batch.http_status = getattr(exc, "status", 502)
                    batch.retry_after = getattr(exc, "retry_after", None)
            health.finish_station(
                outcome,
                batch,
                records,
                rejected,
                received,
                client.requests - requests,
                error,
                successes=client.successful_requests - successes,
            )
        if batch.rejected:
            batch.complete = False
        batch.native_evidence_asof = health.required_asof(batch.environment)
    else:
        checked = await nps(client, batch, stations, max_pages, now, checkpoint)
        progress = {**(progress or {}), "parks_checked_at": checked}
        if batch.rejected:
            batch.complete = False
    if progress is not None and batch.complete and not batch.rejected:
        batch.checkpoint = {**progress, "scope_hash": scope_hash}
    # Freshness uses native evidence/issue time. Government publications without
    # a native timestamp remain unknown, even following a successful HTTP read.
    stamps = [
        f.valid_at if f.evidence_kind == "measurement" else f.issued_at or f.provider_updated_at
        for f in batch.records
        if not f.withdrawn
    ]
    if key == "nps":
        batch.native_evidence_asof = max((s for s in stamps if s), default=None)
