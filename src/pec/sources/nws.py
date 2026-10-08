"""Formal NWS shadow facts; the existing HA/M1 alert evaluator is untouched."""
from .contracts import PISMO
from .models import Fact, RecordError, finite, polygon, timestamp


def alert(feature):
    props=feature.get("properties") if isinstance(feature,dict) else None
    if not isinstance(props,dict):
        raise RecordError("invalid_alert")
    eid=props.get("id") or feature.get("id")
    if not isinstance(eid,str) or not eid.startswith(("urn:","https://api.weather.gov/alerts/")):
        raise RecordError("invalid_alert_identity")
    if props.get("status")!="Actual" or props.get("messageType") not in ("Alert","Update","Cancel"):
        raise RecordError("unknown_alert_status")
    if not isinstance(props.get("event"),str) or not props["event"]:
        raise RecordError("invalid_alert_event")
    sent=timestamp(props.get("sent"))
    expires=timestamp(props.get("expires"))
    if expires<sent:
        raise RecordError("invalid_alert_interval")
    geometry=feature.get("geometry")
    if geometry is not None:
        polygon(geometry)
    geocode=props.get("geocode") or {}
    same=geocode.get("SAME")
    if geometry is None and (not isinstance(same,list) or not all(isinstance(v,str) and len(v)==6 and v.isdigit() for v in same) or not same):
        raise RecordError("unresolved_alert_geography")
    references=props.get("references") or []
    if not isinstance(references,list) or not all(isinstance(v,dict) and isinstance(v.get("identifier"),str) for v in references):
        raise RecordError("invalid_alert_references")
    metadata=dict(provenance_kind="SOURCE_FACT",proof_role="SAFETY",event=props["event"],
        message_type=props["messageType"],expires=expires.isoformat(),
        supersedes=[v["identifier"] for v in references],active=props["messageType"]!="Cancel",geocode=geocode)
    payload={"id":eid,"geometry":geometry,"properties":{k:props[k] for k in
        ("id","event","sent","expires","onset","ends","status","messageType","severity","references","geocode") if k in props}}
    return Fact(eid,"safety","nws_alert",sent,sent,payload,metadata,
        spatial_basis="area_only",provider_geometry=geometry,analysis_area=geometry)


def forecast(period,updated):
    start=timestamp(period.get("startTime"))
    end=timestamp(period.get("endTime"))
    if end<=start:
        raise RecordError("invalid_forecast_interval")
    temperature=finite(period.get("temperature"),"invalid_temperature")
    unit=period.get("temperatureUnit")
    if unit not in ("F","C"):
        raise RecordError("unknown_temperature_unit")
    value=temperature if unit=="F" else temperature*9/5+32
    if not -150<=value<=160:
        raise RecordError("invalid_temperature")
    metadata=dict(provenance_kind="SOURCE_FACT",proof_role="CONDITION",point_key=PISMO["key"],
        period_start=start.isoformat(),period_end=end.isoformat(),temperature_f=value,
        short_forecast=period.get("shortForecast"),microclimate_proven=False,
        aggregation_proven=False)
    clean={k:period[k] for k in ("startTime","endTime","temperature","temperatureUnit","shortForecast","windSpeed","windDirection") if k in period}
    return Fact(f"forecast:{PISMO['key']}:{start.isoformat()}","condition","forecast_temperature",updated,updated,
        clean,metadata,time_precision="model",spatial_basis="area_only")
