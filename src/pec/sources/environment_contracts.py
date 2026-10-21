"""Batch 2A contracts. Collection never grants photographic or access clearance."""

from dataclasses import replace
from math import ceil

from .contracts import INATURALIST, CONTRACTS

_COMMON = dict(
    authentication="Public government measurement service; NPS requires configured API key",
    roles=("CONDITION", "PLANNING"),
    polling_seconds=3600,
    request_spacing_seconds=1.1,
    requests_per_day=300,
    pagination="Bounded station allowlists and explicit finite time windows; traverse and validate all pages",
    identity="Native dataset/station/series/valid time; forecast issue time is part of forecast identity",
    corrections="Same native identity is revised, previous numerical assertion and provenance retained",
    deletion="Explicit missing/withdrawn values invalidate that identity; absence from a time window never deletes history",
    evidence_time="Measurement valid time, forecast valid time, issue time and receipt time stored separately",
    provider_time="Native modification time only when supplied; otherwise NULL, never HTTP receipt time",
    location="Public station coordinates from provider; no wildlife or public destination inference",
    precision="Station point is instrument location, not catchment coverage or route eligibility",
    geoprivacy="Public hydrology and park publications only; no protected biological geometry",
    counts="Physical quantities and native units; never wildlife counts",
    behavior="No biological or photographic inference",
    quality="Native provisional/estimated/missing/quality flags preserved; invalid numerical values not fabricated",
    freshness_seconds=172800,
    malformed="Reject records with fixed diagnostics; retain valid siblings without certifying incomplete collection",
    can_prove=("Provider-published measurements, forecasts or park information with explicit scope",),
    cannot_prove=(
        "Current photographic opportunity",
        "Safe road or trail",
        "Horsetail Fall flow from Merced gauges",
    ),
    retention="Normalized measurements/revisions/provenance long-term; raw JSON 90 days with bounded opt-in pruning; government attribution retained",
    parser_version="batch2a-2",
    version="batch2a-2",
)

ENVIRONMENT_CONTRACTS = {
    key: replace(INATURALIST, **_COMMON, source_key=key, provider_name=name, interface=url)
    for key, name, url in (
        (
            "usgs_water",
            "USGS Water Data OGC",
            "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items",
        ),
        ("cdec_river", "CDEC river telemetry", "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet"),
        (
            "cdec_rainfall",
            "CDEC precipitation telemetry",
            "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet",
        ),
        ("cdec_snow", "CDEC snow telemetry", "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet"),
        ("nwps", "NOAA NWPS stage/flow", "https://api.water.noaa.gov/nwps/v1"),
        ("nps", "National Park Service", "https://developer.nps.gov/api/v1"),
    )
}
ENVIRONMENT_CONTRACTS["nps"] = replace(
    ENVIRONMENT_CONTRACTS["nps"],
    roles=("PLANNING", "ACCESS"),
    authentication="CORE_NPS_API_KEY sent as X-Api-Key header; never URLs or diagnostics",
    polling_seconds=21600,
    requests_per_day=150,
    precision="Park/subregion publication, not an open-route guarantee",
    freshness_seconds=86400,
)
CONTRACTS.update(ENVIRONMENT_CONTRACTS)


def base_key(key):
    return key.removesuffix("_history")


def history_contract(contract):
    return replace(contract, source_key=contract.source_key + "_history", polling_seconds=3600)


def request_budget(contract, configured_scope=None):
    from .environment_scope import scope
    key = base_key(contract.source_key)
    if key not in ENVIRONMENT_CONTRACTS or key == 'nps':
        return None
    count = 1 if contract.source_key.endswith('_history') else len(scope(configured_scope)[key])
    # USGS: two parameter queries per station plus bounded pagination headroom.
    return max(12, 4 * count) if key == 'usgs_water' else count * (2 if key == 'nwps' else 1)


def effective_contract(contract, configured_scope=None):
    budget = request_budget(contract, configured_scope)
    if budget is None:
        return contract
    interval = max(contract.polling_seconds, ceil(budget * 86400 / contract.requests_per_day))
    return replace(contract, polling_seconds=interval)
