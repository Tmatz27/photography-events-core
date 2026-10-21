"""R1–R3 adversarial synthetic regressions; never claimed as live evidence."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from pec.ingestion import fingerprint
from pec.sources.environment_contracts import (
    ENVIRONMENT_CONTRACTS,
    effective_contract,
    history_contract,
    request_budget,
)
from pec.sources.environment_scope import scope
from pec.sources.environment_health import coverage, history_health
from pec.sources.fetch import fetch
from pec.sources.http import Response, FetchError, NativeFloat, read
from pec.sources import environment_models as m
from test_batch2a_portable import NOW, cdec_row, usgs_row, nwps_section, fake


def checkpoint(options=None, **values):
    return dict(scope_hash=fingerprint(scope(options)), **values)


async def test_R1_consecutive_empty_cdec_days_advance_then_measurements_resume():
    options = {"history_start": "2026-10-12", "history_end": "2026-10-15"}
    progress = {}
    for day in (12, 13, 14):
        client, calls = await fake("cdec_snow", [[] if day < 14 else [cdec_row()]])
        client.contract = history_contract(client.contract)
        client.collection_scope = options
        batch = await fetch(client.contract, client, NOW, checkpoint=progress)
        assert batch.complete and batch.http_status == 200 and len(calls) == 1
        station = batch.environment["stations"][0]
        assert station["outcome"] == ("no_observations" if day < 14 else "data")
        assert station["window_start"].startswith(f"2026-10-{day}")
        assert len(batch.records) == int(day == 14)
        progress = json.loads(json.dumps(batch.checkpoint))  # persisted/reloaded shape
        assert progress["next_start"] > station["window_start"]


@pytest.mark.parametrize("body", [Response(500, {}), {}, [None], [{"stationId": "GIN"}]])
async def test_R1_invalid_or_failed_empty_lookalike_never_advances(body):
    client, _ = await fake("cdec_snow", [body])
    client.contract = history_contract(client.contract)
    batch = await fetch(client.contract, client, NOW)
    assert not batch.complete and batch.checkpoint is None
    assert batch.environment["stations"][0]["outcome"] in ("failed", "incomplete")


async def test_R1_partial_cdec_station_failure_preserves_later_healthy_sibling():
    client, _ = await fake("cdec_snow", [Response(503, {}), [cdec_row()]])
    client.collection_scope = {"cdec_snow": ["BAD", "GIN"]}
    batch = await fetch(client.contract, client, NOW)
    assert not batch.complete and batch.http_status == 503 and batch.checkpoint is None
    assert len(batch.records) == 1 and batch.records[0].station_id == "GIN"
    result = coverage(batch.environment, NOW, client.contract)
    assert [s["state"] for s in result["stations"]] == ["failed", "current"]


async def nwps_batch(observed_age=0, forecast_age=0, absent=False):
    client, _ = await fake(
        "nwps",
        [
            dict(lid="POHC1", latitude=37.7, longitude=-119.6),
            dict(
                observed={
                    **nwps_section(),
                    "data": []
                    if absent
                    else [
                        dict(
                            validTime=(NOW - timedelta(days=observed_age)).isoformat(),
                            generatedTime=NOW.isoformat(),
                            primary=4.125,
                            secondary=0.123,
                        )
                    ],
                },
                forecast={
                    **nwps_section(),
                    "issuedTime": (NOW - timedelta(days=forecast_age)).isoformat(),
                    "data": [
                        dict(
                            validTime=(NOW + timedelta(days=1)).isoformat(),
                            generatedTime=NOW.isoformat(),
                            primary=5.25,
                            secondary=0.25,
                        )
                    ],
                },
            ),
        ],
    )
    batch = await fetch(client.contract, client, NOW)
    return batch, coverage(batch.environment, NOW, client.contract)


@pytest.mark.parametrize(
    "obs,forecast,absent,measured,issued,aggregate",
    [
        (5, 0, False, "stale", "current", "stale"),
        (0, 5, False, "current", "stale", "stale"),
        (0, 0, False, "current", "current", "current"),
        (0, 0, True, "unknown", "current", "unknown"),
    ],
)
async def test_R2_measurement_and_forecast_freshness_independent(
    obs, forecast, absent, measured, issued, aggregate
):
    from pec.sources.debug import freshness

    batch, result = await nwps_batch(obs, forecast, absent)
    assert batch.complete
    assert result["measurement_freshness"] == measured and result["forecast_freshness"] == issued
    assert (
        freshness(
            ENVIRONMENT_CONTRACTS["nwps"],
            dict(
                enabled=True,
                status="success",
                incomplete=False,
                provider_updated_at=NOW,
                native_evidence_asof=batch.native_evidence_asof,
                completed_at=NOW,
            ),
            NOW,
        )
        == aggregate
    )
    facts = [f for f in batch.records if f.evidence_kind == "forecast"]
    assert len(facts) == 2 and facts[0].valid_at == NOW + timedelta(days=1)
    assert facts[0].issued_at == NOW - timedelta(days=forecast) and facts[0].numeric_value == Decimal("5.25")
    assert facts[0].issued_at.isoformat() in facts[0].external_id


def feature_collection(station=None, malformed=False, at=NOW):
    row = usgs_row()
    row["properties"].update(monitoring_location_id=station, time=at.isoformat())
    rows = [row] if station else []
    if malformed:
        rows.insert(0, None)
    return dict(type="FeatureCollection", features=rows, numberReturned=len(rows), links=[])


async def usgs_batch(states, *, at=NOW):
    stations = ["USGS-11109000", "USGS-11264500", "USGS-11266500"][: len(states)]
    pages = []
    for station, state in zip(stations, states):
        if state == "failed":
            pages.append(Response(503, {}))
        else:
            pages.extend(
                [feature_collection(station if state == "current" else None, at=at), feature_collection()]
            )
    client, calls = await fake("usgs_water", pages)
    client.collection_scope = {"usgs_water": stations}
    progress = checkpoint(client.collection_scope, incremental_end=at.isoformat())
    batch = await fetch(client.contract, client, NOW, checkpoint=progress)
    return batch, coverage(batch.environment, NOW, client.contract), calls


@pytest.mark.parametrize(
    "states,expected",
    [
        (["current", "silent", "silent"], ["current", "no_observations", "no_observations"]),
        (["silent", "silent", "silent"], ["no_observations"] * 3),
        (["current"], ["current"]),
        (["current", "failed", "current"], ["current", "failed", "current"]),
    ],
)
async def test_R3_station_request_success_and_measurement_coverage(states, expected):
    batch, result, calls = await usgs_batch(states)
    assert [s["state"] for s in result["stations"]] == expected
    assert len(batch.records) == states.count("current")
    assert result["successful_stations"] == len(states) - states.count("failed")
    assert result["measurement_freshness"] == ("current" if set(states) == {"current"} else "unknown")
    assert batch.native_evidence_asof == (NOW if set(states) == {"current"} else None)
    assert len(calls) == 2 * len(states) - states.count("failed")
    assert batch.complete == ("failed" not in states)
    assert bool(batch.checkpoint) == batch.complete


async def test_R3_silent_station_recovers_without_carrying_success_from_sibling():
    _, before, _ = await usgs_batch(["silent", "current"])
    batch, after, _ = await usgs_batch(["current", "current"])
    assert before["measurement_freshness"] == "unknown"
    assert after["measurement_freshness"] == "current" and batch.native_evidence_asof == NOW


async def test_R3_successful_request_for_old_incremental_window_reports_stale():
    batch, result, _ = await usgs_batch(["current"], at=NOW - timedelta(days=5))
    assert batch.complete and result["stations"][0]["state"] == "stale"
    assert result["measurement_freshness"] == "stale"


async def test_malformed_usgs_sibling_retained_without_checkpoint():
    client, _ = await fake(
        "usgs_water", [feature_collection("USGS-11264500", malformed=True), feature_collection()]
    )
    client.collection_scope = {"usgs_water": ["USGS-11264500"]}
    batch = await fetch(client.contract, client, NOW)
    assert len(batch.records) == 1 and batch.rejected and not batch.complete and batch.checkpoint is None
    assert batch.environment["stations"][0]["outcome"] == "incomplete"


@pytest.mark.parametrize("key", ["cdec_river", "nwps", "nps"])
async def test_malformed_sibling_isolated_for_remaining_batch2a_providers(key):
    if key == "cdec_river":
        values = [[None, {**cdec_row(1), "date": "2026-10-14 10:00", "obsDate": "2026-10-14 10:00"}]]
    elif key == "nwps":
        values = [
            dict(lid="POHC1", latitude=37.7, longitude=-119.6),
            dict(
                observed={
                    **nwps_section(),
                    "data": [
                        None,
                        dict(
                            validTime=NOW.isoformat(), generatedTime=NOW.isoformat(), primary=1, secondary=2
                        ),
                    ],
                },
                forecast={**nwps_section(), "data": []},
            ),
        ]
    else:
        values = [
            dict(
                data=[
                    None,
                    dict(
                        id="ok", parkCode="yose", title="Official alert", description="Dated official content"
                    ),
                ],
                total="2",
                start="0",
                limit="50",
            )
        ]
    client, _ = await fake(key, values)
    client.provider_secrets = {"CORE_NPS_API_KEY": "not-real"}
    progress = checkpoint(parks_checked_at=NOW.isoformat()) if key == "nps" else {}
    batch = await fetch(client.contract, client, NOW, checkpoint=progress)
    assert batch.records and batch.rejected and not batch.complete and batch.checkpoint is None
    if key == "nps":
        assert batch.records[-1].metadata["snapshot_complete"] is False


def test_archived_evidence_age_does_not_define_history_worker_health():
    contract = history_contract(ENVIRONMENT_CONTRACTS["nwps"])
    row = dict(
        enabled=True,
        status="success",
        incomplete=False,
        completed_at=NOW,
        native_evidence_asof=NOW - timedelta(days=29),
        provider_updated_at=None,
    )
    from pec.sources.debug import freshness

    assert freshness(contract, row, NOW) == "current"
    assert history_health(row, NOW + timedelta(hours=3), 3600) == "stale"
    assert history_health({**row, "incomplete": True}, NOW, 3600) == "unknown"


@pytest.mark.parametrize("key,count", [("usgs_water", 8), ("nwps", 12), ("cdec_snow", 12)])
def test_valid_large_scopes_fit_daily_quota_with_bounded_pagination(key, count):
    ids = (
        [f"USGS-{i:08}" for i in range(count)]
        if key == "usgs_water"
        else [f"A{i:02}" for i in range(count)]
        if key.startswith("cdec")
        else [f"AAA{i:02}" for i in range(count)]
    )
    options = {key: ids}
    contract = effective_contract(ENVIRONMENT_CONTRACTS[key], options)
    budget = request_budget(contract, options)
    assert budget >= count * (2 if key in ("usgs_water", "nwps") else 1)
    assert budget * 86400 / contract.polling_seconds <= contract.requests_per_day == 300
    assert effective_contract(contract, options) == contract


async def test_request_budget_stops_before_reserving_or_contacting_provider():
    client, calls = await fake("cdec_snow", [[], []])
    client.request_limit = 1
    await client.get(client.contract.interface, allow_list=True)
    with pytest.raises(FetchError, match="collection_request_budget_exhausted"):
        await client.get(client.contract.interface, allow_list=True)
    assert len(calls) == client.requests == 1


async def test_RetryAfter_stops_sibling_requests_and_preserves_failure():
    client, calls = await fake("usgs_water", [Response(429, {}, retry_after="600")])
    batch = await fetch(client.contract, client, NOW)
    assert len(calls) == 1 and batch.http_status == 429 and batch.retry_after == "600"
    assert len(batch.environment["stations"]) == 3 and not batch.checkpoint


@pytest.mark.parametrize("value", ["1.2345678901234567890123456789", "1.200000000000000000e-7"])
def test_native_json_decimal_token_is_retained_for_cdec_and_nwps(value):
    decoded = json.loads('{"value":' + value + "}", parse_float=NativeFloat)["value"]
    cdec = m.cdec(cdec_row(value=decoded), "cdec_snow")
    nwps = m.nwps(
        dict(validTime=NOW.isoformat(), generatedTime=NOW.isoformat(), primary=decoded),
        nwps_section(),
        "observed",
        "POHC1",
        "primary",
        None,
    )
    for fact in (cdec, nwps):
        assert fact.native_value == value and fact.numeric_value == Decimal(value)
    assert json.loads(json.dumps(dict(point=decoded)))  # ordinary JSONB remains compatible


async def test_real_http_decoder_preserves_numbers_only_when_requested():
    class Content:
        async def iter_chunked(self, size):
            yield b'{"value":1.234567890123456789}'

    class HTTPResponse:
        status = 200
        content = Content()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return HTTPResponse()

    plain = await read("https://cdec.water.ca.gov/", "test-agent", session=Session())
    exact = await read("https://cdec.water.ca.gov/", "test-agent", session=Session(), preserve_numbers=True)
    assert type(plain.body["value"]) is float
    assert exact.body["value"].native_text == "1.234567890123456789"


@pytest.mark.parametrize("hours,expected", [(48, "current"), (49, "stale")])
def test_cdec_daily_threshold_remains_truthful(hours, expected):
    from pec.sources.environment_health import age

    assert age(NOW - timedelta(hours=hours), NOW, 172800) == expected
