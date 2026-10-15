"""Synthetic parser/failure cases. These are NEVER live evidence."""

import asyncio
import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pec.sources.environment_contracts import ENVIRONMENT_CONTRACTS, history_contract
from pec.sources.environment_scope import scope, PARKS
from pec.sources import environment_models as m
from pec.sources.environment_fetch import window
from pec.sources.fetch import fetch
from pec.sources.http import Client, Response, FetchError
from pec.sources.models import RecordError

NOW = datetime(2026, 10, 14, 18, tzinfo=UTC)


def usgs_row(value="1.234567890123456789"):
    return {
        "type": "Feature",
        "id": "native-feature",
        "geometry": {"type": "Point", "coordinates": [-119.6, 37.7]},
        "properties": {
            "time_series_id": "native-series",
            "monitoring_location_id": "USGS-11264500",
            "parameter_code": "00060",
            "time": NOW.isoformat(),
            "last_modified": NOW.isoformat(),
            "value": value,
            "unit_of_measure": "ft^3/s",
            "approval_status": "Provisional",
            "qualifier": "estimated",
        },
    }


def cdec_row(sensor=3, value=4.25):
    units = "FEET" if sensor == 1 else "CFS" if sensor == 20 else "INCHES"
    return dict(
        stationId="POH" if sensor in (1, 20) else "GIN",
        SENSOR_NUM=sensor,
        durCode="E" if sensor in (1, 20) else "D",
        date="2026-10-14 00:00",
        obsDate="2026-10-14 00:00",
        value=value,
        units=units,
        dataFlag="r",
        sensorType="native",
    )


def nwps_section():
    return dict(
        issuedTime=NOW.isoformat(),
        pedts="HGIRG",
        primaryName="Stage",
        primaryUnits="ft",
        secondaryName="Flow",
        secondaryUnits="kcfs",
        timeZone="PST8PDT",
    )


def test_native_decimal_units_identity_and_public_station_point():
    fact = m.usgs(usgs_row())
    assert fact.numeric_value == Decimal("1.234567890123456789")
    assert fact.unit == "ft^3/s" and fact.quantity == "discharge" and fact.observed_at == NOW
    assert fact.provider_updated_at == NOW and fact.analysis_point is None
    row = usgs_row()
    row["id"] = "different-transport-id"
    assert m.usgs(row).external_id == fact.external_id


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "NaN", "Infinity", "garbage"])
def test_invalid_numbers_are_never_zero(value):
    with pytest.raises(RecordError):
        m.usgs(usgs_row(value))


@pytest.mark.parametrize(
    "dataset,sensor,quantity",
    [
        ("cdec_river", 1, "gauge_height"),
        ("cdec_river", 20, "discharge"),
        ("cdec_rainfall", 2, "precipitation_accumulation"),
        ("cdec_rainfall", 45, "precipitation_increment"),
        ("cdec_snow", 3, "snow_water_equivalent"),
        ("cdec_snow", 18, "snow_depth"),
        ("cdec_snow", 82, "snow_water_equivalent_adjusted"),
    ],
)
def test_cdec_native_sensor_semantics_and_fixed_pst(dataset, sensor, quantity):
    fact = m.cdec(cdec_row(sensor), dataset)
    assert fact.quantity == quantity and fact.valid_at.astimezone(UTC).hour == 8
    assert fact.provider_updated_at is None and fact.metadata["quality"]["dataFlag"] == "r"
    assert fact.numeric_value == Decimal("4.25") and fact.provider_geometry is None


@pytest.mark.parametrize("value", [-9999, None, "---"])
def test_explicit_missing_value_is_withdrawal_not_a_measurement(value):
    fact = m.cdec(cdec_row(value=value), "cdec_snow")
    assert fact.withdrawn and fact.numeric_value is None
    assert fact.native_value == (str(value) if value is not None else None)


def test_forecast_issue_and_valid_time_do_not_become_observation():
    section = nwps_section()
    row = dict(
        validTime=(NOW + timedelta(days=1)).isoformat(),
        generatedTime=NOW.isoformat(),
        primary=4,
        secondary=0.125,
    )
    forecast = m.nwps(row, section, "forecast", "POHC1", "secondary", None)
    observed = m.nwps(row, section, "observed", "POHC1", "secondary", None)
    assert forecast.evidence_kind == "forecast" and forecast.observed_at is None
    assert forecast.valid_at == NOW + timedelta(days=1) and forecast.issued_at == NOW
    assert forecast.unit == "kcfs" and forecast.numeric_value == Decimal("0.125")
    assert forecast.external_id != observed.external_id
    assert (
        m.nwps(
            row,
            {**section, "issuedTime": (NOW + timedelta(hours=1)).isoformat()},
            "forecast",
            "POHC1",
            "secondary",
            None,
        ).external_id
        != forecast.external_id
    )


def test_native_units_and_coordinates_fail_closed():
    row = usgs_row()
    row["properties"]["unit_of_measure"] = "cubic cats"
    with pytest.raises(RecordError):
        m.usgs(row)
    row = usgs_row()
    row["geometry"]["coordinates"] = [999, 37]
    with pytest.raises(RecordError):
        m.usgs(row)


def test_all_nine_parks_share_eight_official_api_codes():
    assert len(PARKS) == 8 and "seki" in PARKS
    assert set(scope()["nps"]) == set(PARKS)
    with pytest.raises(ValueError):
        scope({"nps": ["yose"]})
    for value in (
        {"usgs_water": []},
        {"nwps": ["https://evil.invalid"]},
        {"bad": []},
        {"history_start": "2026-10-14", "history_end": "2025-01-01"},
    ):
        with pytest.raises(ValueError):
            scope(value)


def test_incremental_restart_uses_persisted_window_frontier_instead_of_receipt_clock():
    options = scope()
    prior = NOW - timedelta(days=20)
    start, end, checkpoint = window(
        "usgs_water", options, {"incremental_end": prior.isoformat()}, NOW, NOW, False
    )
    assert start == prior - timedelta(hours=1) and end - start == timedelta(days=1)
    assert checkpoint["incremental_end"] == end.isoformat() and end < NOW


def test_history_checkpoint_independent_station_and_time_progress():
    options = scope()
    start, end, p = window("usgs_water", options, {}, NOW, None, True)
    assert p["station_index"] == 1 and p["next_start"] == start.isoformat()
    start2, end2, p2 = window("usgs_water", options, p, NOW, None, True)
    assert (start, end) == (start2, end2) and p2["station_index"] == 2
    assert history_contract(ENVIRONMENT_CONTRACTS["usgs_water"]).source_key == "usgs_water_history"


async def fake(key, values):
    calls = []

    async def transport(url, agent):
        calls.append(url)
        value = values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value if isinstance(value, Response) else Response(200, value, 100)

    async def reserve():
        pass

    client = Client(
        ENVIRONMENT_CONTRACTS[key], "PhotographyEventsCore-test", transport=transport, reserve=reserve
    )
    return client, calls


async def test_missing_nps_key_makes_no_provider_requests():
    client, calls = await fake("nps", [])
    batch = await fetch(client.contract, client, NOW)
    assert batch.failure_code == "credentials_needed" and not batch.complete and not calls


async def test_nps_all_park_information_and_true_empty_alert_snapshot():
    parks = [
        dict(id=p, parkCode=p, fullName=p, operatingHours=[{"description": "official hours"}]) for p in PARKS
    ]
    client, calls = await fake(
        "nps",
        [dict(data=[], total="0", start="0", limit="50"), dict(data=parks, total="8", start="0", limit="50")],
    )
    client.provider_secrets = {"CORE_NPS_API_KEY": "fixture-only-secret"}
    batch = await fetch(client.contract, client, NOW)
    assert batch.complete and len(batch.records) == 10
    assert all(r.provider_updated_at is None and r.observed_at is None for r in batch.records)
    assert not any("fixture-only-secret" in url for url in calls)


@pytest.mark.parametrize(
    "total,start,values",
    [("4", "0", []), ("1", "1", []), ("0", "0", [{"id": "unknown", "parkCode": "evil"}])],
)
async def test_nps_incomplete_or_wrong_scope_never_certifies_empty(total, start, values):
    client, _ = await fake("nps", [dict(data=values, total=total, start=start, limit="50")])
    client.provider_secrets = {"CORE_NPS_API_KEY": "fixture-key"}
    batch = await fetch(client.contract, client, NOW)
    assert not batch.complete


async def test_genuine_http_failure_and_retry_after_preserved():
    client, _ = await fake("usgs_water", [Response(429, {}, retry_after="600")])
    batch = await fetch(client.contract, client, NOW)
    assert not batch.complete and batch.http_status == 429 and batch.retry_after == "600"
    assert batch.rate_limited == 1 and batch.checkpoint is None


async def test_usgs_untrusted_pagination_and_changed_window_rejected():
    row = usgs_row()
    row["properties"]["monitoring_location_id"] = "USGS-11109000"
    for url in (
        "https://evil.invalid/x",
        "https://api.waterdata.usgs.gov/evil?monitoring_location_id=USGS-11109000&parameter_code=00060&datetime=wrong",
    ):
        client, _ = await fake(
            "usgs_water",
            [
                dict(
                    type="FeatureCollection",
                    features=[row],
                    numberReturned=1,
                    links=[{"rel": "next", "href": url}],
                )
            ],
        )
        batch = await fetch(client.contract, client, NOW)
        assert not batch.complete and batch.checkpoint is None


async def test_cancellation_propagates():
    client, _ = await fake("usgs_water", [asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await fetch(client.contract, client, NOW)


async def test_cdec_wrong_station_and_empty_feed_remain_failed():
    for rows in ([{**cdec_row(1), "stationId": "BAD"}], []):
        client, _ = await fake("cdec_river", [rows])
        batch = await fetch(client.contract, client, NOW)
        assert not batch.complete and batch.checkpoint is None


async def test_nps_header_secret_and_redirect_do_not_escape_origin():
    contract = ENVIRONMENT_CONTRACTS["nps"]
    client, _ = await fake("nps", [])
    with pytest.raises(FetchError):
        await client.get("https://evil.invalid/x", headers={"X-Api-Key": "secret"})
    assert replace(contract, source_key="nps_history").interface == contract.interface


def test_park_information_is_a_versioned_reference_not_season_api():
    row = dict(
        id="park", parkCode="yose", fullName="Yosemite", operatingHours=[], weatherInfo="official context"
    )
    fact = m.nps(copy.deepcopy(row), "parks")
    assert fact.evidence_kind == "reference" and fact.numeric_value is None
    assert fact.metadata["current_access_proven"] is False


async def test_nps_planning_reference_weekly_refresh_separate_from_alerts():
    from pec.ingestion import fingerprint

    client, calls = await fake("nps", [dict(data=[], total="0", start="0", limit="50")])
    client.provider_secrets = {"CORE_NPS_API_KEY": "fixture-only"}
    checkpoint = dict(scope_hash=fingerprint(scope()), parks_checked_at=(NOW - timedelta(days=1)).isoformat())
    batch = await fetch(client.contract, client, NOW, checkpoint=checkpoint)
    assert batch.complete and len(calls) == 1 and "/alerts?" in calls[0]
    assert batch.checkpoint["parks_checked_at"] == checkpoint["parks_checked_at"]


async def test_completed_history_preserves_scope_hash_without_restarting_from_beginning():
    from pec.ingestion import fingerprint

    client, calls = await fake("usgs_water", [])
    client.contract = history_contract(client.contract)
    client.collection_scope = {"history_start": "2026-01-01", "history_end": "2026-02-01"}
    checkpoint = dict(
        scope_hash=fingerprint(scope(client.collection_scope)),
        next_start="2026-02-01T00:00:00Z",
        station_index=0,
        complete=True,
    )
    batch = await fetch(client.contract, client, NOW, checkpoint=checkpoint)
    assert batch.complete and not calls and batch.checkpoint == checkpoint
