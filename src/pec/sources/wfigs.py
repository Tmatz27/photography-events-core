"""Current public ArcGIS perimeter facts; mapped fire is never road-closure proof."""
from datetime import UTC, datetime

from .models import Fact, RecordError, finite, identifier, polygon

FIELDS=("OBJECTID","GlobalID","poly_IRWINID","poly_FeatureCategory","poly_FeatureStatus",
    "poly_FeatureAccess","poly_IsVisible","poly_DeleteThis","poly_DateCurrent","poly_PolygonDateTime",
    "attr_IncidentTypeCategory","attr_ActiveFireCandidate","attr_FireOutDateTime","attr_ModifiedOnDateTime_dt")


def epoch(value):
    try:
        return datetime.fromtimestamp(finite(value,"invalid_provider_time")/1000,UTC)
    except (ValueError,OverflowError,OSError):
        raise RecordError("invalid_provider_time") from None


def parse(feature):
    if not isinstance(feature,dict) or not isinstance(feature.get("properties"),dict):
        raise RecordError("invalid_feature")
    props=feature["properties"]
    gid=identifier(props.get("GlobalID"))
    irwin=identifier(props["poly_IRWINID"]) if props.get("poly_IRWINID") else None
    eid="irwin:"+irwin if irwin else "global:"+gid
    fire_type=props.get("attr_IncidentTypeCategory")
    if fire_type not in ("WF","RX"):
        raise RecordError("unknown_fire_type")
    active=props.get("attr_ActiveFireCandidate")
    if type(active) is not int or active not in (0,1):
        raise RecordError("unknown_fire_currentness")
    category=props.get("poly_FeatureCategory")
    if category not in ("Wildfire Daily Fire Perimeter","Wildfire Final Fire Perimeter",
                         "Prescribed Fire Perimeter","Prescribed Fire Final Perimeter"):
        raise RecordError("unknown_perimeter_category")
    for field,allowed in (("poly_FeatureStatus",("Approved","Proposed","Draft")),
                          ("poly_FeatureAccess",("Public","Internal","Restricted")),
                          ("poly_IsVisible",("Yes","No")),("poly_DeleteThis",("Yes","No"))):
        if props.get(field) not in allowed:
            raise RecordError("unknown_perimeter_status")
    geometry=polygon(feature.get("geometry"))
    observed=epoch(props.get("poly_PolygonDateTime") or props.get("poly_DateCurrent"))
    updated=epoch(props.get("attr_ModifiedOnDateTime_dt") or props.get("poly_DateCurrent"))
    out=props.get("attr_FireOutDateTime")
    if out is not None:
        epoch(out)
    qualifies=(fire_type=="WF" and active==1 and out is None and "Final" not in category
        and props["poly_FeatureStatus"]=="Approved" and props["poly_FeatureAccess"]=="Public"
        and props["poly_IsVisible"]=="Yes" and props["poly_DeleteThis"]=="No")
    payload={"type":"Feature","properties":{k:props[k] for k in FIELDS if k in props},"geometry":geometry}
    metadata=dict(provenance_kind="SOURCE_FACT",incident_id=irwin,polygon_global_ids=[gid],
        fire_type=fire_type,perimeter_category=category,active_candidate=bool(active),
        qualifying_current_wildfire=qualifies,proof_role="SAFETY",road_closure_proven=False)
    return Fact(eid,"safety","wildfire_perimeter",observed,updated,payload,metadata,
                time_precision="model",spatial_basis="area_only",provider_geometry=geometry,analysis_area=geometry)


def combine(records,rejected=None):
    """Pieces of one incident in the bounded result set are not independent fires."""
    grouped={}
    for record in records:
        grouped.setdefault(record.external_id,[]).append(record)
    answer=[]
    for eid,parts in sorted(grouped.items()):
        if len({r.metadata["fire_type"] for r in parts})!=1:
            if rejected is not None:
                rejected.extend((eid,"inconsistent_incident_type") for _ in parts)
                continue
            raise RecordError("inconsistent_incident_type")
        eligible=[r for r in parts if r.metadata["qualifying_current_wildfire"]]
        selected=eligible or parts
        first=max(selected,key=lambda r:(r.provider_updated_at,r.observed_at))
        polygons=[]
        for r in selected:
            area=r.analysis_area
            polygons.extend([area["coordinates"]] if area["type"]=="Polygon" else area["coordinates"])
        geometry={"type":"MultiPolygon","coordinates":polygons}
        first.payload={"incident_id":eid,"pieces":[r.payload for r in sorted(parts,key=lambda r:r.metadata["polygon_global_ids"][0])]}
        first.metadata={**first.metadata,"polygon_global_ids":sorted({g for r in parts for g in r.metadata["polygon_global_ids"]}),
                        "qualifying_current_wildfire":bool(eligible)}
        first.analysis_area=geometry
        first.provider_geometry=geometry
        answer.append(first)
    return answer
