"""Native numerical assertions do not enter biological normalized_observations."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .models import Fact, RecordError, timestamp, point

PST = timezone(timedelta(hours=-8), "PST")


def number(value):
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        result = Decimal(native_text(value))
        if not result.is_finite():
            raise ValueError()
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise RecordError("invalid_measurement_value") from None


def native_text(value):
    return getattr(value, 'native_text', str(value))


def text_id(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise RecordError("invalid_environment_identity")
    return value


def coordinate(geometry):
    if geometry is not None:
        point(geometry)
    return geometry


@dataclass
class EnvironmentalFact(Fact):
    dataset_key: str = ""
    station_id: str = ""
    quantity: str = ""
    evidence_kind: str = "measurement"
    valid_at: datetime | None = None
    issued_at: datetime | None = None
    native_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    withdrawn: bool = False


def make(
    dataset,
    identity,
    station,
    quantity,
    payload,
    *,
    kind="measurement",
    valid=None,
    updated=None,
    issued=None,
    value=None,
    unit=None,
    geometry=None,
    quality=None,
    metadata=None,
    withdrawn=False,
):
    if kind in ("measurement", "forecast") and (not unit or valid is None):
        raise RecordError("missing_measurement_unit_or_time")
    if kind == "forecast" and issued is None:
        raise RecordError("missing_forecast_issue_time")
    return EnvironmentalFact(
        text_id(identity),
        kind,
        quantity,
        valid if kind == "measurement" else None,
        updated,
        payload,
        dict(quality=quality or {}, **(metadata or {})),
        provider_geometry=coordinate(geometry),
        dataset_key=dataset,
        station_id=text_id(station),
        quantity=quantity,
        evidence_kind=kind,
        valid_at=valid,
        issued_at=issued,
        native_value=native_text(value) if value is not None else None,
        numeric_value=number(value) if value is not None and not withdrawn else None,
        unit=unit,
        withdrawn=withdrawn,
    )


USGS_PARAMETERS = {"00060": ("discharge", "ft^3/s"), "00065": ("gauge_height", "ft")}


def usgs(feature):
    p = feature["properties"]
    quantity, unit = USGS_PARAMETERS[p["parameter_code"]]
    if p["unit_of_measure"] != unit:
        raise RecordError("unexpected_usgs_unit")
    valid = timestamp(p["time"])
    # Native time-series + valid time survives an upstream feature-ID change.
    series = text_id(p["time_series_id"])
    missing = p["value"] is None or p["value"] in ("", "Ice", "Eqp", "Ssn", "***")
    return make(
        "usgs_water",
        f"{series}:{valid.isoformat()}",
        p["monitoring_location_id"],
        quantity,
        feature,
        valid=valid,
        updated=timestamp(p["last_modified"]),
        value=p["value"],
        unit=unit,
        geometry=feature.get("geometry"),
        withdrawn=missing,
        quality={k: p.get(k) for k in ("approval_status", "qualifier", "method_category")},
        metadata={
            "native_feature_id": feature.get("id"),
            "time_series_id": series,
            "statistic_id": p.get("statistic_id"),
            "parameter_code": p["parameter_code"],
        },
    )


CDEC_PARAMETERS = {
    "cdec_river": {1: ("gauge_height", "FEET"), 20: ("discharge", "CFS")},
    "cdec_rainfall": {45: ("precipitation_increment", "INCHES"), 2: ("precipitation_accumulation", "INCHES")},
    "cdec_snow": {
        3: ("snow_water_equivalent", "INCHES"),
        18: ("snow_depth", "INCHES"),
        82: ("snow_water_equivalent_adjusted", "INCHES"),
    },
}


def cdec(row, dataset):
    quantity, unit = CDEC_PARAMETERS[dataset][row["SENSOR_NUM"]]
    if row["units"] != unit or row["durCode"] not in ("H", "D", "E"):
        raise RecordError("unexpected_cdec_unit_or_duration")
    # CDEC timestamps are fixed Pacific STANDARD time, including summer.
    valid = datetime.strptime(row["obsDate"], "%Y-%m-%d %H:%M").replace(tzinfo=PST)
    scheduled = datetime.strptime(row["date"], "%Y-%m-%d %H:%M").replace(tzinfo=PST)
    identity = f"{row['stationId']}:{row['SENSOR_NUM']}:{row['durCode']}:{scheduled.isoformat()}"
    value = row["value"]
    missing = (
        value is None
        or str(value).strip() in ("", "---", "--", "m", "ART", "BRT")
        or (isinstance(value, (int, float)) and value <= -999)
    )
    return make(
        dataset,
        identity,
        row["stationId"],
        quantity,
        row,
        valid=valid,
        value=value,
        unit=unit,
        withdrawn=missing,
        quality={"dataFlag": row.get("dataFlag"), "sensorType": row.get("sensorType")},
        metadata={
            "native_time_zone": "PST (UTC-08:00)",
            "scheduled_at": scheduled.isoformat(),
            "duration": row["durCode"],
            "sensor_number": row["SENSOR_NUM"],
            "provider_modification_time_available": False,
            "station_geometry": "not supplied by data endpoint",
        },
    )


def nwps(row, section, product, station, dimension, geometry):
    name = section[dimension + "Name"]
    unit = section[dimension + "Units"]
    if (name, unit) not in (("Stage", "ft"), ("Flow", "kcfs"), ("Flow", "cfs")):
        raise RecordError("unexpected_nwps_quantity_unit")
    valid = timestamp(row["validTime"])
    issued = timestamp(section["issuedTime"])
    updated = timestamp(row["generatedTime"])
    value = row.get(dimension)
    missing = value is None or number(value) == Decimal(-9999)
    identity = f"{station}:{section['pedts']}:{dimension}:{product}:{valid.isoformat()}"
    if product == "forecast":
        identity += ":" + issued.isoformat()
    return make(
        "nwps",
        identity,
        station,
        name.lower(),
        row,
        kind="forecast" if product == "forecast" else "measurement",
        valid=valid,
        issued=issued if product == "forecast" else None,
        updated=updated,
        value=value,
        unit=unit,
        geometry=geometry,
        withdrawn=missing,
        quality={"pedts": section["pedts"]},
        metadata={
            "product": product,
            "primaryName": section.get("primaryName"),
            "native_time_zone": section.get("timeZone"),
            "usgs_mirror_possible": True,
        },
    )


def nps(row, endpoint):
    park = text_id(row["parkCode"])
    identity = text_id(row["id"])
    if not row.get("title" if endpoint == "alerts" else "fullName"):
        raise RecordError("missing_nps_title")
    if endpoint == "alerts" and row.get("category") not in (
        "Park Closure",
        "Closure",
        "Caution",
        "Danger",
        "Information",
    ):
        raise RecordError("unknown_nps_alert_category")
    modified = row.get("lastIndexedDate")
    # lastIndexedDate is an indexing timestamp, not an ecological observation.
    updated = timestamp(modified) if modified else None
    return make(
        "nps",
        f"{endpoint}:{identity}",
        park,
        "park_alert" if endpoint == "alerts" else "park_information",
        row,
        kind="publication" if endpoint == "alerts" else "reference",
        updated=updated,
        quality={"category": row.get("category")},
        metadata={
            "endpoint": endpoint,
            "native_indexed_at": modified,
            "current_access_proven": False,
            "reference_content": {
                k: row[k]
                for k in (
                    "id",
                    "parkCode",
                    "title",
                    "description",
                    "category",
                    "fullName",
                    "operatingHours",
                    "weatherInfo",
                    "directionsInfo",
                    "entranceFees",
                    "entrancePasses",
                    "url",
                    "addresses",
                )
                if k in row
            },
            "planning_fields": [
                k
                for k in (
                    "operatingHours",
                    "weatherInfo",
                    "directionsInfo",
                    "entranceFees",
                    "addresses",
                    "url",
                )
                if k in row
            ],
        },
    )
