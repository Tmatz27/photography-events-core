"""Source-controlled contracts describe facts and limits, never DB executable policy."""
from dataclasses import asdict, dataclass

from ..patterns.policy import canonical_hash
from ..scheduler import Policy


@dataclass(frozen=True)
class SourceContract:
    source_key: str
    provider_name: str
    interface: str
    roles: tuple[str,...]
    authentication: str
    polling_seconds: int
    request_spacing_seconds: float
    requests_per_day: int
    pagination: str
    identity: str
    corrections: str
    deletion: str
    evidence_time: str
    provider_time: str
    location: str
    precision: str
    geoprivacy: str
    counts: str
    behavior: str
    quality: str
    freshness_seconds: int
    malformed: str
    can_prove: tuple[str,...]
    cannot_prove: tuple[str,...]
    retention: str
    parser_version: str = "public-contract-1"
    version: str = "m3a-1"

    @property
    def hash(self):
        return canonical_hash(asdict(self))

    @property
    def scheduler_policy(self):
        return Policy(minimum_interval=self.polling_seconds,timeout=120)


# Vandenberg/Santa Barbara/San Luis Obispo first travel slice, not all California.
# Pismo point is the accepted HA c76726e conditions.py point; association radius
# is a provisional product parameter, not a surveyed grove/ecological boundary.
BOUNDS=(-121.3,34.2,-119.0,36.2)
PISMO=dict(key="pismo_grove",name="Pismo State Beach Monarch Butterfly Grove",
           latitude=35.1307,longitude=-120.6349,association_meters=500,
           public_listing="https://www.parks.ca.gov/?page_id=30273")
TAXA={41638:"Ursus americanus",48662:"Danaus plexippus"}
RETENTION="Existing bounded application sweep; raw bulk 90d, identity metadata retained; no new normalized purge/partition; episodes long-term; revisit after measured volume"
MALFORMED="Reject individual record with fixed diagnostic codes; valid siblings persist; incomplete safety collection never proves absence"

INATURALIST=SourceContract(
    "inaturalist","iNaturalist","https://api.inaturalist.org/v1/observations",
    ("DISCOVERY","WATCH_SIGNAL","CORROBORATION"),"Public read; no OAuth/private-coordinate access",
    1800,1.05,10000,"per_page=200, order_by=id ascending, id_above; bounded pages; explicit ID-list refresh",
    "UUID is source external identity; numeric ID retained for bulk refresh; no fuzzy identity",
    "Verified updated_since plus overlapping observed-date/taxon/bbox search; refresh bounded relevant known numeric IDs to discover scope/taxon corrections",
    "No public deletion tombstone assumed; missing ID in complete explicit-ID read means public-unavailable, not proven deletion",
    "time_observed_at UTC when full/aware; otherwise observed_on date stored separately with DATE precision and no invented observed_at",
    "updated_at kept separately from fetched_at; polling cursor is query progress, never evidence time",
    "Only provider-returned public GeoJSON; no raw point is a public destination",
    "Open with known acceptable public accuracy can enter density; unknown accuracy/date-only excluded from tight points",
    "Union coordinates_obscured/geoprivacy/taxon_geoprivacy; obscured random 0.2-degree-cell point is raw public geometry only; private geometry unavailable",
    "Presence only; reported_count NULL; neither prose nor report counts become animal totals",
    "Presence only; controlled annotations retained as source values without unverified mappings; description is never canonical feeding/cubs confirmation",
    "Research/needs_id/casual and provider lineage retained; Research Grade may corroborate, lower confidence is discovery/watch only",
    86400,MALFORMED,
    ("Provider observation presence, community taxon, quality and publicly supplied spatial/time basis",),
    ("Confirmed behavior","Individual totals","Independent observers","Hidden coordinates","Major monarch grove count","Travel eligibility"),RETENTION)
WFIGS=SourceContract(
    "wfigs_current","NIFC / WFIGS","https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0",
    ("SAFETY","CONDITION"),"Public ArcGIS read",900,1.05,2000,
    "Object-ID snapshot then bounded GeoJSON ID batches; verify IDs/exceededTransferLimit; snapshot edit recheck",
    "IRWIN UUID incident identity; GlobalID fallback perimeter identity; OBJECTID only transport metadata; incident pieces union within query scope",
    "Complete bounded current snapshot corrects geometry/currentness; retain old versions; no duplicate independent fire from incident refresh",
    "Only complete valid scope snapshot retires absent current facts; absence is no longer in this view, not proven incident deletion",
    "poly_PolygonDateTime / poly_DateCurrent = model perimeter time",
    "attr_ModifiedOnDateTime_dt / poly_DateCurrent plus service dataLastEditDate; never replaced by HTTP retrieval time",
    "GeoJSON polygons/MultiPolygons in EPSG:4326; actual destination intersection only",
    "Mapped perimeter, not exact physical flame boundary; no arbitrary universal buffer or route inference",
    "Public fire geometry; no biological private-coordinate acquisition",
    "Incident/feature metadata only; no biological count", "Not applicable",
    "WF versus RX, approved/public/visible, active candidate; final/historic excluded; unknown required enum rejects",
    10800,MALFORMED,
    ("Current qualifying wildfire perimeter intersects an approved destination: shadow hold candidate",),
    ("Road closure","Safe travel from no intersection","Biological activity","Historic perimeter is active wildfire"),RETENTION)
NWS=SourceContract(
    "nws_live_context","National Weather Service","https://api.weather.gov; existing HA alerts interface plus one Pismo grid forecast context",
    ("CONDITION","SAFETY"),"Descriptive User-Agent/contact URL; no paid API key",900,1.05,2000,
    "Alert pagination.next restricted to api.weather.gov; forecast hourly periods; no unbounded redirect",
    "CAP alert ID and explicit references; forecast grid/approved point plus period start",
    "CAP Update/Cancel references and native forecast updateTime; preserve working HA/M1 NWS behavior unchanged",
    "Active collection absence/expiry is not proof alert never existed",
    "Alert sent/onset/expiry and forecast issue/valid period, separately",
    "Collection updated/native updateTime; stale native data stays stale after HTTP success",
    "Alert geography and approved forecast point/grid; forecast is not measured grove microclimate",
    "Area/grid model; temperature condition only; no hidden wildlife location",
    "Public weather information", "Not applicable", "Cannot prove wildlife behavior",
    "Actual alert message/status and readable forecast units/periods",10800,MALFORMED,
    ("Published alerts","Forecast temperature/wind/cloud conditions at the grid",),
    ("Actual monarch clustering","Wildlife behavior","Exact grove microclimate","55F creates aggregation or universal Can't Miss"),RETENTION)
CONTRACTS={c.source_key:c for c in (INATURALIST,WFIGS,NWS)}
