"""Public v1 observation facts: presence, actual time precision and geoprivacy."""
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import BOUNDS, TAXA
from .models import Fact, RecordError, finite, identifier, point, timestamp

PUBLIC_FIELDS=("id","uuid","time_observed_at","observed_on","observed_time_zone","updated_at",
    "quality_grade","geoprivacy","taxon_geoprivacy","coordinates_obscured","obscured",
    "public_positional_accuracy","geojson","taxon","community_taxon_id","annotations","description")


def parse(record):
    if not isinstance(record,dict):
        raise RecordError("invalid_record")
    eid=identifier(record.get("uuid"))
    pid=record.get("id")
    if type(pid) is not int or not 0<pid<10**18:
        raise RecordError("invalid_numeric_id")
    taxon=record.get("taxon")
    if (not isinstance(taxon,dict) or type(taxon.get("id")) is not int
            or not isinstance(taxon.get("name"),str) or not taxon["name"].strip()
            or not isinstance(taxon.get("ancestor_ids"),list)
            or not all(type(v) is int for v in taxon["ancestor_ids"])):
        raise RecordError("invalid_taxon")
    roots=[root for root in TAXA if root in {taxon["id"],*taxon["ancestor_ids"]}]
    if len(roots)>1:
        raise RecordError("invalid_taxon")
    subject=TAXA[roots[0]] if roots else taxon["name"]
    quality=record.get("quality_grade")
    if quality not in ("research","needs_id","casual"):
        raise RecordError("unknown_quality_grade")
    zone=record.get("observed_time_zone")
    if zone is not None:
        try:
            ZoneInfo(zone)
        except (TypeError,ValueError,ZoneInfoNotFoundError):
            raise RecordError("invalid_observation_timezone") from None
    observed=None
    observed_date=None
    precision="timestamp"
    if record.get("time_observed_at"):
        observed=timestamp(record["time_observed_at"],"invalid_observed_time")
    else:
        try:
            observed_date=date.fromisoformat(record["observed_on"])
        except (KeyError,TypeError,ValueError):
            raise RecordError("invalid_observed_date") from None
        precision="date"
    updated=timestamp(record.get("updated_at"),"invalid_provider_update")
    privacy=[record.get("geoprivacy"),record.get("taxon_geoprivacy")]
    if any(v not in (None,"open","obscured","private") for v in privacy):
        raise RecordError("unknown_geoprivacy")
    obscured=record.get("coordinates_obscured",record.get("obscured",False))
    if type(obscured) is not bool:
        raise RecordError("invalid_geoprivacy_flag")
    basis="private_unavailable" if "private" in privacy else "obscured_cell" if obscured or "obscured" in privacy else "open_point"
    geometry=None
    coordinate=None
    if basis!="private_unavailable" and record.get("geojson") is not None:
        coordinate=point(record["geojson"])
        geometry={"type":"Point","coordinates":list(coordinate)}
    if coordinate is None and basis=="open_point":
        basis="private_unavailable"
    accuracy=record.get("public_positional_accuracy")
    if accuracy is not None:
        accuracy=finite(accuracy,"invalid_accuracy")
        if accuracy<0:
            raise RecordError("invalid_accuracy")
    # No ordinary observation or arbitrary field/prose is a typed count.
    # Unknown count-looking values are retained nowhere in the normalized count.
    if "reported_count" in record and record["reported_count"] is not None:
        if type(record["reported_count"]) is not int or record["reported_count"]<0:
            raise RecordError("malformed_count")
    annotations=record.get("annotations",[])
    if not isinstance(annotations,list) or not all(isinstance(v,dict) for v in annotations):
        raise RecordError("invalid_annotations")
    if any(type(a.get(k)) is not int or a[k]<=0 for a in annotations for k in ('controlled_attribute_id','controlled_value_id')):
        raise RecordError('invalid_annotations')
    if record.get('community_taxon_id') is not None and (type(record['community_taxon_id']) is not int or record['community_taxon_id']<=0):
        raise RecordError('invalid_taxon')
    clean_annotations=[{k:a[k] for k in ("controlled_attribute_id","controlled_value_id") if k in a} for a in annotations]
    clean_taxon={k:taxon[k] for k in ("id","name","rank","ancestor_ids") if k in taxon}
    payload={k:record[k] for k in PUBLIC_FIELDS if k in record and k not in ("taxon","annotations","geojson")}
    payload.update(taxon=clean_taxon,annotations=clean_annotations,geojson=geometry)
    if payload.get("description") is not None and not isinstance(payload["description"],str):
        raise RecordError("invalid_description")
    metadata=dict(provenance_kind="SOURCE_FACT",provider_numeric_id=pid,taxon=clean_taxon,
        community_taxon_id=record.get("community_taxon_id"),quality_grade=quality,
        geoprivacy=record.get("geoprivacy"),taxon_geoprivacy=record.get("taxon_geoprivacy"),
        coordinates_obscured=obscured,annotations=clean_annotations,presence=True,
        proof_role="CORROBORATION" if quality=="research" else "WATCH_SIGNAL",
        count_basis="unknown",behavior_basis="presence_only")
    inside=bool(roots)
    if coordinate is not None:
        inside &= BOUNDS[0]<=coordinate[0]<=BOUNDS[2] and BOUNDS[1]<=coordinate[1]<=BOUNDS[3]
    precise=(coordinate if basis=="open_point" and accuracy is not None and precision=="timestamp" else None)
    return Fact(eid,"species",subject,observed,updated,payload,metadata,
        observed_date=observed_date,observed_time_zone=zone,time_precision=precision,
        spatial_basis=basis,provider_geometry=geometry,analysis_point=precise,uncertainty=accuracy,
        sensitive=basis!="open_point",credible=quality=="research",in_scope=inside)
