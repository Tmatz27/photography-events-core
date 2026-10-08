"""Offline provider acceptance: faithful field topology, fictional identities/points."""

import copy
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from pec.config import Settings
from pec.scheduler import State, next_state
from pec.sources import inaturalist, nws, wfigs
from pec.sources.calibration import POLICIES_SHADOW, condition
from pec.sources.contracts import CONTRACTS, INATURALIST, NWS, WFIGS
from pec.sources.debug import freshness
from pec.sources.fetch import fetch, observation_params
from pec.sources.http import Client, FetchError, Response
from pec.sources.models import Batch, RecordError

FIXTURES = Path(__file__).parent / "fixtures/providers"
NOW = datetime(2026, 9, 27, 17, tzinfo=UTC)


def observation(index=1, subject="monarch", **changes):
    record = copy.deepcopy(json.loads((FIXTURES / "inaturalist.json").read_text())["results"][0])
    record.update(
        id=index,
        uuid=f"00000000-0000-4000-8000-{index:012d}",
        quality_grade="research",
        time_observed_at=NOW.isoformat(),
        observed_on=NOW.date().isoformat(),
        updated_at=NOW.isoformat(),
    )
    if subject == "bear":
        record["taxon"] = dict(id=41638, name="Ursus americanus", ancestor_ids=[1, 41638], rank="species")
    record.update(changes)
    return record


def perimeter(index=1, **changes):
    feature = copy.deepcopy(json.loads((FIXTURES / "wfigs.json").read_text())["features"][0])
    epoch = int(NOW.timestamp() * 1000)
    feature["id"] = index
    feature["properties"].update(
        OBJECTID=index,
        GlobalID=f"{{00000000-0000-4000-8000-{index:012d}}}",
        poly_IRWINID=f"{{00000000-0000-4000-9000-{index:012d}}}",
        poly_DateCurrent=epoch,
        poly_PolygonDateTime=epoch,
        attr_ModifiedOnDateTime_dt=epoch,
        attr_FireOutDateTime=None,
    )
    feature["properties"].update(changes)
    return feature


def alert(index=1, **changes):
    result = dict(
        type="Feature",
        geometry=perimeter()["geometry"],
        properties=dict(
            id=f"urn:test:{index}",
            status="Actual",
            messageType="Alert",
            event="Red Flag Warning",
            sent=NOW.isoformat(),
            expires=(NOW + timedelta(hours=3)).isoformat(),
            references=[],
        ),
    )
    result["properties"].update(changes)
    return result


def forecast(temperature=50, **changes):
    result = dict(
        startTime=NOW.isoformat(),
        endTime=(NOW + timedelta(hours=1)).isoformat(),
        temperature=temperature,
        temperatureUnit="F",
        shortForecast="Sunny",
    )
    result.update(changes)
    return result


async def noop():
    pass


def client(contract, responses):
    calls = []

    async def transport(url, ua):
        calls.append((url, ua))
        value = responses.pop(0)
        return value if isinstance(value, Response) else Response(200, value, 100)

    return Client(
        contract, "PhotographyEventsCore-offline-contract-tests", reserve=noop, transport=transport
    ), calls


@pytest.mark.parametrize("key", CONTRACTS)
def test_contract_complete_source_controlled(key):
    value = asdict(CONTRACTS[key])
    assert len(value) >= 26 and all(v for v in value.values())
    assert len(CONTRACTS[key].hash) == 64
    assert "ACCESS" not in value["roles"]


def test_i1_open_research_grade():
    fact = inaturalist.parse(observation())
    assert fact.analysis_point and fact.credible and fact.reported_count is None
    assert fact.metadata["proof_role"] == "CORROBORATION"


def test_i2_obscured_raw_public_point_only():
    fact = inaturalist.parse(observation(obscured=True, public_positional_accuracy=1))
    assert fact.provider_geometry and not fact.analysis_point and fact.sensitive
    assert fact.spatial_basis == "obscured_cell"


def test_i3_private_no_invented_point():
    fact = inaturalist.parse(observation(geoprivacy="private", geojson=None))
    assert fact.provider_geometry is None and fact.analysis_point is None


def test_i7_one_bad_among_200():
    values = [observation(i + 1) for i in range(200)]
    values[30]["uuid"] = None
    batch = Batch()
    batch.parse(values, inaturalist.parse)
    assert len(batch.records) == 199 and len(batch.rejected) == 1 and batch.received == 200


def test_i10_date_precision():
    fact = inaturalist.parse(observation(time_observed_at=None))
    assert fact.observed_at is None and fact.observed_date == NOW.date() and fact.time_precision == "date"
    assert fact.analysis_point is None


def test_i11_b4_no_text_behavior_or_count():
    fact = inaturalist.parse(
        observation(subject="bear", description="feeding sow with cubs; 3 bears", reported_count=3)
    )
    assert fact.metadata["behavior_basis"] == "presence_only" and fact.reported_count is None
    assert "sow with cubs" in fact.payload["description"]


def test_i12_grade_role():
    facts = [inaturalist.parse(observation(quality_grade=g)) for g in ("research", "needs_id", "casual")]
    assert [f.credible for f in facts] == [True, False, False]
    assert [f.metadata["proof_role"] for f in facts] == ["CORROBORATION", "WATCH_SIGNAL", "WATCH_SIGNAL"]


@pytest.mark.parametrize(
    "change,code",
    [
        ({"uuid": "bad"}, "invalid_identity"),
        ({"id": None}, "invalid_numeric_id"),
        ({"time_observed_at": "naive"}, "invalid_observed_time"),
        ({"updated_at": None}, "invalid_provider_update"),
        ({"geojson": {"type": "Point", "coordinates": [float("nan"), 35]}}, "invalid_coordinate"),
        ({"geoprivacy": "secret"}, "unknown_geoprivacy"),
        ({"taxon": {}}, "invalid_taxon"),
        ({"reported_count": "X"}, "malformed_count"),
        ({"quality_grade": "new"}, "unknown_quality_grade"),
        ({"public_positional_accuracy": -1}, "invalid_accuracy"),
        ({"coordinates_obscured": "false"}, "invalid_geoprivacy_flag"),
    ],
)
def test_observation_schema_drift_is_fixed_code(change, code):
    with pytest.raises(RecordError, match=code):
        inaturalist.parse(observation(**change))


def test_optional_fields_missing_unknown_accuracy_no_precise_point():
    r = observation()
    for key in ("description", "annotations", "observed_time_zone", "public_positional_accuracy"):
        r.pop(key, None)
    fact = inaturalist.parse(r)
    assert not fact.analysis_point and fact.uncertainty is None


def test_private_fields_and_user_details_not_retained():
    r = observation(
        private_geojson={"type": "Point", "coordinates": [1, 2]},
        user={"login": "PII"},
        photos=[{"secret": "token"}],
    )
    body = json.dumps(inaturalist.parse(r).payload)
    assert "PII" not in body and "private_geojson" not in body and "token" not in body


async def test_inaturalist_pagination_and_actual_incremental_parameters():
    c, calls = client(
        INATURALIST,
        [
            dict(total_results=201, results=[observation(i) for i in range(1, 201)]),
            dict(total_results=1, results=[observation(201)]),
        ],
    )
    batch = await fetch(INATURALIST, c, NOW, cursor=NOW)
    assert batch.complete and len(batch.records) == 201
    params = parse_qs(urlparse(calls[1][0]).query)
    assert params["id_above"] == ["200"] and params["per_page"] == ["200"] and params["updated_since"]
    assert "updated_since" in observation_params(NOW, NOW)


async def test_inaturalist_scope_correction_explicit_refresh():
    r = observation()
    r["taxon"] = dict(id=1, name="Animalia", ancestor_ids=[1])
    c, calls = client(INATURALIST, [dict(total_results=0, results=[]), dict(total_results=1, results=[r])])
    batch = await fetch(INATURALIST, c, NOW, known={1: r["uuid"]})
    assert batch.complete and not batch.records[0].in_scope
    assert "taxon_id" not in parse_qs(urlparse(calls[-1][0]).query)


async def test_complete_explicit_refresh_absence_public_unavailable():
    c, _ = client(INATURALIST, [dict(total_results=0, results=[]), dict(total_results=0, results=[])])
    batch = await fetch(INATURALIST, c, NOW, known={1: observation()["uuid"]})
    assert batch.unavailable_ids == {observation()["uuid"]}


@pytest.mark.parametrize("contract", [INATURALIST, NWS, WFIGS])
async def test_i9_n2_429_backoff(contract):
    c, _ = client(contract, [Response(429, {}, retry_after="7200")])
    batch = await fetch(contract, c, NOW)
    assert not batch.complete and batch.http_status == 429 and batch.rate_limited == 1
    state = next_state(
        contract.scheduler_policy,
        State(NOW),
        NOW,
        success=False,
        retry_after=batch.retry_after,
        jitter=lambda: 0,
    )
    assert state.next_allowed_at >= NOW + timedelta(hours=2)


def test_w3_prescribed_and_w4_final_not_current_block():
    assert not wfigs.parse(perimeter(attr_IncidentTypeCategory="RX")).metadata["qualifying_current_wildfire"]
    assert not wfigs.parse(perimeter(poly_FeatureCategory="Wildfire Final Fire Perimeter")).metadata[
        "qualifying_current_wildfire"
    ]


def test_w6_malformed_siblings_continue():
    batch = Batch()
    batch.parse([perimeter(), perimeter(2, attr_IncidentTypeCategory="unknown"), perimeter(3)], wfigs.parse)
    assert len(batch.records) == 2 and len(batch.rejected) == 1


def test_same_irwin_pieces_not_independent_incidents():
    a, b = perimeter(), perimeter(2)
    b["properties"]["poly_IRWINID"] = a["properties"]["poly_IRWINID"]
    assert len(wfigs.combine([wfigs.parse(a), wfigs.parse(b)])) == 1


def test_bad_incident_group_does_not_kill_other_groups():
    a, b = perimeter(), perimeter(2, attr_IncidentTypeCategory="RX")
    b["properties"]["poly_IRWINID"] = a["properties"]["poly_IRWINID"]
    errors = []
    facts = wfigs.combine([wfigs.parse(a), wfigs.parse(b), wfigs.parse(perimeter(3))], errors)
    assert len(facts) == 1 and len(errors) == 2


async def test_w7_snapshot_max_record_count():
    meta = dict(
        geometryType="esriGeometryPolygon",
        fields=[{"name": k} for k in wfigs.FIELDS],
        maxRecordCount=1,
        editingInfo={"dataLastEditDate": int(NOW.timestamp() * 1000)},
    )
    c, calls = client(
        WFIGS,
        [meta, dict(objectIds=[1, 2]), dict(features=[perimeter()]), dict(features=[perimeter(2)]), meta],
    )
    batch = await fetch(WFIGS, c, NOW)
    assert batch.complete and batch.snapshot and len(batch.records) == 2 and len(calls) == 5


async def test_partial_perimeter_page_keeps_good_never_proves_absence():
    meta = dict(
        geometryType="esriGeometryPolygon",
        fields=[{"name": k} for k in wfigs.FIELDS],
        maxRecordCount=2000,
        editingInfo={"dataLastEditDate": int(NOW.timestamp() * 1000)},
    )
    c, _ = client(
        WFIGS,
        [
            meta,
            dict(objectIds=[1, 2]),
            dict(features=[perimeter()], properties={"exceededTransferLimit": True}),
        ],
    )
    batch = await fetch(WFIGS, c, NOW)
    assert not batch.complete and len(batch.records) == 1 and not batch.snapshot


async def test_perimeter_required_schema_drift_no_empty_success():
    c, _ = client(WFIGS, [{"fields": []}])
    batch = await fetch(WFIGS, c, NOW)
    assert not batch.complete and batch.failure_code == "perimeter_schema_drift"


def test_n3_explicit_update_reference():
    fact = nws.alert(alert(2, messageType="Update", references=[{"identifier": "urn:test:1"}]))
    assert fact.metadata["supersedes"] == ["urn:test:1"]


def test_n4_success_does_not_make_stale_forecast_fresh():
    assert (
        freshness(
            NWS,
            dict(
                enabled=True, status="success", incomplete=False, provider_updated_at=NOW - timedelta(days=1)
            ),
            NOW,
        )
        == "stale"
    )


def test_n5_m3_m4_temperature_only_condition():
    cool = nws.forecast(forecast(50), NOW)
    warm = nws.forecast(forecast(70), NOW)
    assert not cool.metadata["aggregation_proven"] and not warm.metadata["microclimate_proven"]
    assert "clustered" in condition(50) and "not invalidated" in condition(70)


async def test_n1_user_agent_and_untrusted_next_host():
    c, calls = client(
        NWS, [dict(type="FeatureCollection", features=[], pagination={"next": "https://evil.example/token"})]
    )
    batch = await fetch(NWS, c, NOW)
    assert calls[0][1].startswith("PhotographyEvents") and batch.failure_code == "untrusted_pagination_url"
    assert "limit" not in parse_qs(urlparse(calls[0][0]).query)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.weather.gov/alerts",
        "https://user:secret@api.weather.gov/alerts",
        "https://api.weather.gov:444/alerts",
    ],
)
async def test_no_credentials_redirect_or_untrusted_transport(url):
    c, _ = client(NWS, [])
    with pytest.raises(FetchError, match="untrusted_pagination_url"):
        await c.get(url)


def test_shadow_only_settings_and_provisional_policy():
    with pytest.raises(ValueError, match="shadow"):
        Settings("postgresql+asyncpg://localhost/test", "a" * 40, live_sources=True)
    assert not Settings("postgresql+asyncpg://localhost/test", "a" * 40).live_sources
    assert all(p.calibration_only and p.version == "m3a-calibration-1" for p in POLICIES_SHADOW)
    assert len(POLICIES_SHADOW) == 2
