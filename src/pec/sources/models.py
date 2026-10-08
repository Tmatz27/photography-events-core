"""Normalized source-neutral facts retain actual temporal/spatial precision."""
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta


class RecordError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__(code)


def timestamp(value,code="invalid_timestamp"):
    try:
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(UTC)
    except (AttributeError,ValueError,TypeError,OverflowError):
        raise RecordError(code) from None


def identifier(value,code="invalid_identity"):
    try:
        if not isinstance(value,str):
            raise ValueError()
        return str(uuid.UUID(value.strip("{}")))
    except (ValueError,TypeError,AttributeError):
        raise RecordError(code) from None


def finite(value,code):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise RecordError(code)
    return float(value)


def point(geometry):
    if not isinstance(geometry,dict) or geometry.get("type")!="Point":
        raise RecordError("invalid_coordinate")
    values=geometry.get("coordinates")
    if not isinstance(values,list) or len(values)!=2:
        raise RecordError("invalid_coordinate")
    lon,lat=(finite(v,"invalid_coordinate") for v in values)
    if not -180<=lon<=180 or not -90<=lat<=90:
        raise RecordError("invalid_coordinate")
    return lon,lat


def polygon(geometry):
    if not isinstance(geometry,dict) or geometry.get("type") not in ("Polygon","MultiPolygon"):
        raise RecordError("invalid_polygon")
    polygons=[geometry.get("coordinates")] if geometry["type"]=="Polygon" else geometry.get("coordinates")
    if not isinstance(polygons,list) or not polygons:
        raise RecordError("invalid_polygon")
    for rings in polygons:
        if not isinstance(rings,list) or not rings:
            raise RecordError("invalid_polygon")
        for ring in rings:
            if not isinstance(ring,list) or len(ring)<4 or ring[0]!=ring[-1]:
                raise RecordError("invalid_polygon")
            for pair in ring:
                point({"type":"Point","coordinates":pair})
            if len({tuple(pair) for pair in ring})<3:
                raise RecordError("invalid_polygon")
    return geometry


@dataclass
class Fact:
    external_id: str
    subject_type: str
    subject_key: str
    observed_at: datetime | None
    provider_updated_at: datetime
    payload: dict
    metadata: dict
    observed_date: date | None = None
    observed_time_zone: str | None = None
    time_precision: str = "timestamp"
    spatial_basis: str = "unknown"
    provider_geometry: dict | None = None
    analysis_point: tuple[float,float] | None = None
    analysis_area: dict | None = None
    uncertainty: float | None = None
    sensitive: bool = False
    credible: bool = False
    in_scope: bool = True
    reported_count: int | None = None

    @property
    def valid_until(self):
        if self.subject_type=="condition":
            return timestamp(self.metadata["period_end"])
        if self.subject_type=="safety":
            return timestamp(self.metadata["expires"]) if self.metadata.get("expires") else self.provider_updated_at+timedelta(days=15)
        if self.observed_at is not None:
            return self.observed_at+timedelta(days=14)
        # This is an expiry envelope for a DATE, never an invented observation
        # instant. Unknown timezone permits the latest UTC-12 end of that date.
        return datetime.combine(self.observed_date+timedelta(days=15),time(),UTC)+timedelta(hours=12)


@dataclass
class Batch:
    records: list[Fact] = field(default_factory=list)
    rejected: list[tuple[str | None,str]] = field(default_factory=list)
    received: int = 0
    requests: int = 0
    bytes_received: int = 0
    complete: bool = True
    http_status: int = 200
    retry_after: str | None = None
    provider_updated_at: datetime | None = None
    rate_limited: int = 0
    unavailable_ids: set[str] = field(default_factory=set)
    snapshot: bool = False
    failure_code: str | None = None
    alert_asof: datetime | None = None

    def parse(self,values,parser):
        for value in values:
            self.received+=1
            try:
                self.records.append(parser(value))
            except RecordError as exc:
                eid=None
                if isinstance(value,dict):
                    try:
                        eid=identifier(value.get("uuid"))
                    except RecordError:
                        pass
                    props=value.get('properties')
                    if isinstance(props,dict):
                        if props.get('poly_IRWINID') or props.get('GlobalID'):
                            try:
                                irwin=props.get('poly_IRWINID')
                                eid=('irwin:' if irwin else 'global:')+identifier(irwin or props.get('GlobalID'))
                            except RecordError:
                                pass
                        elif isinstance(props.get('id'),str) and props['id'].startswith(('urn:','https://api.weather.gov/alerts/')):
                            eid=props['id']
                self.rejected.append((eid,exc.code))
            except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
                self.rejected.append((None,"invalid_record"))
