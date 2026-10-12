"""Full approved ingestion program; a scope entry is never a working adapter."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    batch: int
    kind: str = 'live'
    credentials: tuple[str, ...] = ()
    legacy: str | None = None
    access: str = 'public'
    measurements: tuple[str, ...] = ()
    evidence_kind: str = 'provider contract pending'
    adapter: str | None = None
    ranked_priority: int | None = None
    retention: str = 'Normalized history retained; licensed raw/archive policy requires provider validation'
    historical_coverage: str = 'Not yet verified for Core coverage area'
    upstream_lineage: str = 'Native upstream identity must be retained; independence is not inferred from adapter count'


PROVIDERS = (
    Provider('inaturalist', 'iNaturalist', 1, legacy='observations.py'),
    Provider('nws_live_context', 'NWS alerts and forecast', 1, legacy='weather_hazards.py / conditions.py'),
    Provider('wfigs_current', 'NIFC/WFIGS current wildfire perimeters', 1),
    Provider('usgs_water', 'USGS Water Data OGC', 2, legacy='streamflow.py',measurements=('discharge','water_level'),evidence_kind='measurement',ranked_priority=1),
    Provider('cdec', 'CDEC dataset family', 2,kind='group'),
    Provider('nwps', 'NOAA NWPS', 2,measurements=('river_forecast','flood_context'),evidence_kind='forecast',ranked_priority=17),
    Provider('nps', 'NPS alerts, access and closures', 2, credentials=('CORE_NPS_API_KEY',), legacy='parks.py'),
    Provider('caltrans', 'Caltrans QuickMap/ArcGIS road and chain-control context', 2,measurements=('road_access','chain_control'),evidence_kind='published road condition',ranked_priority=9),
    Provider('open_meteo', 'Open-Meteo forecast and cloud layers', 2, legacy='conditions.py'),
    Provider('open_meteo_air_quality', 'Open-Meteo air quality', 2),
    Provider('sunsetwx', 'SunsetWx Sunburst', 2,
        credentials=('CORE_SUNSETWX_CLIENT_ID', 'CORE_SUNSETWX_CLIENT_SECRET'), legacy='sunburst.py', access='subscription'),
    Provider('ovation', 'NOAA OVATION aurora nowcast', 2, legacy='conditions.py'),
    Provider('goes18', 'GOES-18 ABI-L2 cloud/fog products', 2,measurements=('cloud','fog_context'),evidence_kind='satellite-derived product',ranked_priority=12),
    Provider('hpwren', 'HPWREN dataset family', 2,kind='group', access='permitted interface required'),
    Provider('hpwren_cameras', 'HPWREN camera images', 2,access='image/archive rights and approved camera allowlist required',measurements=('visual_conditions',),evidence_kind='camera observation; no invented visual labels',ranked_priority=7),
    Provider('hpwren_weather', 'HPWREN weather station observations', 2,access='permitted station interface required',measurements=('weather',),evidence_kind='measurement'),
    Provider('ebird_notable', 'eBird notable observations', 3, credentials=('CORE_EBIRD_API_KEY',), legacy='birds.py'),
    Provider('ebird_species', 'eBird species observations', 3, credentials=('CORE_EBIRD_API_KEY',), legacy='birds.py'),
    Provider('birdcast', 'BirdCast migration products', 3, access='approved data interface/storage rights required', measurements=('bird_migration',),evidence_kind='radar-derived model',ranked_priority=5),
    Provider('nexrad', 'Independently processed NEXRAD weather radar', 3, access='approved product/pipeline required', measurements=('radar_reflectivity',),evidence_kind='radar observation; biological separation not assumed'),
    Provider('usfws_counts', 'USFWS refuge counts', 3, access='approved reports/interface required',measurements=('waterfowl_count',),evidence_kind='survey; native survey date and refuge scope',ranked_priority=14),
    Provider('usfws_reports', 'USFWS published migration reports', 3,kind='event',access='approved reports/interface required',measurements=('migration_report',),evidence_kind='published field report'),
    Provider('condor_express', 'Condor Express operator reports', 3, legacy='field_reports.py'),
    Provider('field_reports', 'Supported wildlife field reports', 3, kind='event', legacy='email_reports.py / field_reports.py',
        access='trusted ingress; subscriptions/permission required'),
    Provider('email_reports', 'Legacy subscribed email report ingress', 3, kind='event',
        credentials=('CORE_IMAP_HOST', 'CORE_IMAP_USERNAME', 'CORE_IMAP_PASSWORD'), legacy='email_reports.py', access='user subscription'),
    Provider('ndbc', 'NOAA NDBC measured offshore conditions', 4, legacy='waves.py'),
    Provider('cdip_models', 'CDIP nearshore wave models', 4, legacy='waves.py',measurements=('wave_height','wave_period','wave_direction'),evidence_kind='model',ranked_priority=11),
    Provider('cdip_measured', 'CDIP measured waves', 4,measurements=('wave_height','wave_period','wave_direction'),evidence_kind='measurement'),
    Provider('coops', 'NOAA CO-OPS dataset family', 4,kind='group', legacy='grunion.py / conditions.py'),
    Provider('coops_predictions', 'NOAA CO-OPS station tide/high-low predictions', 4,legacy='grunion.py / conditions.py',measurements=('tide_height','high_low_time'),evidence_kind='prediction'),
    Provider('coops_water_level', 'NOAA CO-OPS measured station water levels', 4,measurements=('water_level',),evidence_kind='measurement'),
    Provider('calhabmap', 'SCCOOS CalHABMAP', 4,measurements=('harmful_algal_bloom',),evidence_kind='sampling/report; not proof of nighttime bioluminescence',ranked_priority=6),
    Provider('coastwatch_sst', 'NOAA CoastWatch ERDDAP sea surface temperature', 4,measurements=('sea_surface_temperature',),evidence_kind='satellite-derived product',ranked_priority=2),
    Provider('coastwatch_chlorophyll', 'NOAA CoastWatch ERDDAP chlorophyll', 4,measurements=('chlorophyll',),evidence_kind='satellite-derived product'),
    Provider('coastwatch_upwelling', 'NOAA CoastWatch ERDDAP upwelling context', 4,measurements=('upwelling',),evidence_kind='published/model product; dataset contract pending'),
    Provider('mbari_ocean_song', 'MBARI Ocean Song / permitted acoustics', 4,
        credentials=('CORE_MBARI_API_TOKEN',), access='access_pending; approved interface/permission required',measurements=('acoustic_whale_presence',),evidence_kind='acoustic detection',ranked_priority=8),
    Provider('king_tides', 'Published California King Tide dates', 4, kind='reference', legacy='events.py'),
    Provider('grunion', 'CDFW grunion schedules', 4, kind='reference', legacy='grunion.py'),
    Provider('sentinel2', 'Sentinel-2 vegetation dataset family', 5,kind='group',
        credentials=('CORE_COPERNICUS_CLIENT_ID', 'CORE_COPERNICUS_CLIENT_SECRET'), access='approved access path required',ranked_priority=3),
    Provider('sentinel2_ndvi', 'Sentinel-2 NDVI vegetation observations', 5,
        credentials=('CORE_COPERNICUS_CLIENT_ID', 'CORE_COPERNICUS_CLIENT_SECRET'), access='approved access path required',measurements=('ndvi',),evidence_kind='satellite-derived product'),
    Provider('sentinel2_evi', 'Sentinel-2 EVI vegetation observations', 5,
        credentials=('CORE_COPERNICUS_CLIENT_ID', 'CORE_COPERNICUS_CLIENT_SECRET'), access='approved access path required',measurements=('evi',),evidence_kind='satellite-derived product'),
    Provider('theodore_payne', 'Theodore Payne bloom reports', 5, legacy='field_reports.py', access='permitted published report interface required'),
    Provider('desertusa', 'DesertUSA bloom reports', 5, legacy='field_reports.py', access='permitted published report interface required'),
    Provider('california_fall_color', 'California Fall Color reports', 5, legacy='field_reports.py', access='permitted published report interface required'),
    Provider('seasonal_references', 'Other previously approved authoritative seasonal datasets', 5,
        kind='reference', access='Gemini handoff needed to enumerate; scope remains committed'),
    Provider('nasa_eclipses', 'NASA eclipse catalogs and path tables', 5, kind='reference', legacy='eclipse_catalog.json / tools/import_eclipses.py'),
    Provider('meteor_reference', 'Previously adopted meteor shower reference data', 5, kind='reference', legacy='events.py / astronomy.py'),
    Provider('astronomical_inputs', 'Approved astronomical computation inputs', 5, kind='reference', legacy='astronomy.py / lunar.py'),
    Provider('legacy_seasonal_references', 'Legacy authoritative seasonal references (USFWS, Xerces/State Parks, monitored seal colonies)',
        5, kind='reference', legacy='SOURCE_VALIDATION.md / curation.py'),
    Provider('nws_active_alerts', 'NWS Active Alerts', 1,adapter='nws_live_context',measurements=('weather_alert',),evidence_kind='published alert',ranked_priority=4),
    Provider('nws_hourly_forecast', 'NWS hourly forecast context', 1,adapter='nws_live_context',measurements=('temperature','wind'),evidence_kind='forecast'),
    Provider('nws_gridpoints', 'NWS Gridpoints forecast fields', 2,measurements=('cloud_layers','precipitation','snowfall','weather'),evidence_kind='forecast',ranked_priority=13),
    Provider('nws_forecast_discussions', 'NWS forecast discussions', 2,measurements=('forecast_context',),evidence_kind='published forecast interpretation'),
    Provider('inaturalist_plants', 'iNaturalist plant observations', 5,measurements=('plant_presence',),evidence_kind='reported observation; public geometry only'),
    Provider('ebird_checklists', 'eBird checklist reports and counts', 3,credentials=('CORE_EBIRD_API_KEY',),measurements=('bird_presence','reported_count'),evidence_kind='reported observation; no duplicate confirmation from species API'),
    Provider('motus', 'Motus Wildlife Tracking Network', 3,access='permission/credential/license and machine interface pending',measurements=('tagged_bird_detection',),evidence_kind='tag detection; sensitive movement/location restrictions',ranked_priority=16),
    Provider('whale_alert', 'Whale Alert reported sightings', 3,access='machine interface/permission/archive rights pending',measurements=('whale_presence',),evidence_kind='reported sighting',ranked_priority=15),
    Provider('whale_safe', 'Whale Safe', 3,access='provider API inquiry/permission/archive rights pending',measurements=('whale_presence',),evidence_kind='provider product; mixed visual/acoustic/model lineage must be retained'),
    Provider('audubon_reports', 'Local Audubon reports', 3,kind='event',access='approved feeds/publisher permissions required',measurements=('bird_presence','reported_count'),evidence_kind='dated field report'),
    Provider('ranger_reports', 'Approved park ranger/blog reports', 3,kind='event',access='approved feeds/archive rights required',measurements=('field_observation',),evidence_kind='dated field report'),
    Provider('harbor_operator_reports', 'Public harbor/operator reports', 4,kind='event',access='approved feeds/archive rights required',measurements=('marine_conditions','wildlife_presence'),evidence_kind='dated operator report'),
    Provider('approved_rss', 'Other approved RSS feeds', 3,kind='event',access='approved feed allowlist/archive rights required',measurements=('field_observation',),evidence_kind='published report; syndicated identity must be preserved'),
    Provider('cdec_river', 'CDEC river gauges', 2,measurements=('water_level','discharge'),evidence_kind='measurement',ranked_priority=10),
    Provider('cdec_rainfall', 'CDEC rainfall sensors', 2,measurements=('rainfall',),evidence_kind='measurement'),
    Provider('cdec_snow', 'CDEC snow sensors/snowpack', 2,measurements=('snow_depth','snow_water_equivalent'),evidence_kind='measurement',ranked_priority=20),
    Provider('cdec_soil_moisture', 'CDEC soil moisture sensors', 5,measurements=('soil_moisture',),evidence_kind='measurement'),
    Provider('goes_glm', 'GOES GLM lightning observations', 2,measurements=('lightning',),evidence_kind='satellite observation'),
    Provider('county_air_quality', 'County Air Quality District observations', 2,access='approved district feeds/archive rights required',measurements=('air_quality','smoke_visibility_context'),evidence_kind='measurement; pollutant/product-specific',ranked_priority=19),
    Provider('purpleair', 'PurpleAir', 2,credentials=('CORE_PURPLEAIR_API_KEY',),access='credential/plan/archive rights required',measurements=('particulate_matter',),evidence_kind='sensor measurement; calibration and sensor quality retained'),
    Provider('blm', 'BLM ArcGIS land/access restrictions', 2,measurements=('land_access','restrictions'),evidence_kind='published jurisdictional GIS',ranked_priority=18),
    Provider('state_parks_gis', 'California State Parks GIS', 2,measurements=('public_land','restrictions'),evidence_kind='published jurisdictional GIS'),
    Provider('usfs_access', 'USFS roads/closures/access data', 2,measurements=('road_access','restrictions'),evidence_kind='published jurisdictional information'),
    Provider('beach_restrictions', 'Local municipal/county beach restrictions', 2,access='approved local agency datasets/archive rights required',measurements=('beach_closure',),evidence_kind='published jurisdictional information'),
    Provider('cal_fire', 'CAL FIRE incident information', 2,measurements=('wildfire_incident',),evidence_kind='published incident information; shared upstream with WFIGS possible'),
    Provider('watchduty', 'WatchDuty', 2,access='authorized machine interface/permission/archive rights pending',measurements=('wildfire_report',),evidence_kind='reported hazard; official-feed overlap must be identified'),
    Provider('landsat', 'Landsat vegetation observations/indices', 5,measurements=('vegetation_index',),evidence_kind='satellite-derived product'),
    Provider('xerces_monarch', 'Xerces monarch counts and references', 5,kind='reference',access='published count dataset/archive rights required',measurements=('monarch_count','seasonal_reference'),evidence_kind='survey/published reference; native survey date preserved'),
    Provider('state_parks_monarch', 'State Parks monarch reports', 5,kind='event',access='approved published reports required',measurements=('monarch_count',),evidence_kind='dated survey/field report'),
    Provider('elephant_seal_reports', 'Official elephant-seal seasonal/breeding reports', 5,kind='reference',legacy='SOURCE_VALIDATION.md',measurements=('seasonal_reference','reported_count'),evidence_kind='published reference/report; rejected molt phenomenon excluded'),
    Provider('harbor_seal_reports', 'Official harbor-seal seasonal reports', 5,kind='reference',legacy='SOURCE_VALIDATION.md',measurements=('seasonal_reference','reported_count'),evidence_kind='published reference/report'),
    Provider('noaa_solar', 'NOAA solar/space-weather observations', 2,measurements=('solar_weather',),evidence_kind='measurement/model product; distinct from OVATION'),
)
_MEASUREMENTS = {
    'inaturalist': ('reported_presence',), 'inaturalist_plants': ('reported_plant_presence',),
    'wfigs_current': ('mapped_wildfire_perimeter',), 'nws_live_context': ('weather_alert','forecast_temperature'),
    'nps': ('park_alert','access_restriction'), 'open_meteo': ('cloud_layers','wind','temperature','rainfall','snowfall'),
    'open_meteo_air_quality': ('aerosol_optical_depth','air_quality'), 'sunsetwx': ('sunrise_sunset_model_quality',),
    'ovation': ('aurora_nowcast',), 'ebird_notable': ('reported_bird_presence','reported_count'),
    'ebird_species': ('reported_bird_presence','reported_count'), 'condor_express': ('dated_operator_report',),
    'field_reports': ('dated_field_report',), 'email_reports': ('dated_field_report',),
    'ndbc': ('wave_height','wave_period','wave_direction'), 'king_tides': ('published_tide_calendar',),
    'grunion': ('published_run_schedule',), 'theodore_payne': ('dated_bloom_report',),
    'desertusa': ('dated_bloom_report',), 'california_fall_color': ('dated_foliage_report',),
    'seasonal_references': ('published_seasonal_reference',), 'legacy_seasonal_references': ('published_seasonal_reference',),
    'nasa_eclipses': ('eclipse_catalog','eclipse_path_geometry'), 'meteor_reference': ('shower_peak','radiant'),
    'astronomical_inputs': ('lunar_solar_geometry',),
}
_KINDS = {
    'inaturalist':'reported observation; presence only', 'wfigs_current':'published mapped perimeter',
    'nws_live_context':'published alert and model forecast; separate datasets share one accepted collector',
    'nps':'published access restriction', 'open_meteo':'forecast', 'open_meteo_air_quality':'model',
    'sunsetwx':'forecast', 'ovation':'nowcast', 'ebird_notable':'reported observation', 'ebird_species':'reported observation',
    'condor_express':'dated operator report', 'field_reports':'dated field report', 'email_reports':'dated field report',
    'ndbc':'measured offshore observation', 'king_tides':'published calendar', 'grunion':'published schedule',
    'theodore_payne':'published field report', 'desertusa':'published field report', 'california_fall_color':'published field report',
    'nasa_eclipses':'scientific reference catalog', 'meteor_reference':'scientific reference catalog',
    'astronomical_inputs':'versioned computation inputs; no phenomenon scoring',
}
_LINEAGE = {
    **{k:'iNaturalist native observation UUID; API/taxon views do not create independent reports' for k in ('inaturalist','inaturalist_plants')},
    **{k:'eBird checklist/submission/observation identity; API views may repeat the same report' for k in ('ebird_notable','ebird_species','ebird_checklists')},
    **{k:'NEXRAD radar provenance; derived BirdCast and raw radar are complementary, not independent measurements' for k in ('birdcast','nexrad')},
    'nws_active_alerts':'NWS CAP identifier/references; shared with nws_live_context',
    'nws_hourly_forecast':'NWS grid and issue/valid period; shared with nws_live_context',
    'cal_fire':'Official incident identity; potential NIFC/WFIGS overlap must be resolved from explicit metadata',
    'watchduty':'Reporter/official-feed provenance; do not assume independent confirmation',
    'whale_safe':'Retain source detection/report/model lineage; acoustic and visual evidence are distinct',
}
PROVIDERS = tuple(replace(p, measurements=_MEASUREMENTS.get(p.key,p.measurements),
    evidence_kind=_KINDS.get(p.key,p.evidence_kind),upstream_lineage=_LINEAGE.get(p.key,p.upstream_lineage)) for p in PROVIDERS)
INVENTORY = {p.key: p for p in PROVIDERS}
CREDENTIAL_NAMES = frozenset(name for p in PROVIDERS for name in p.credentials)


def configured(provider, secrets):
    return all(bool(secrets.get(name)) for name in provider.credentials)


def selection(value):
    keys = tuple(INVENTORY) if value.strip() == 'all' else tuple(v.strip() for v in value.split(',') if v.strip())
    if len(set(keys)) != len(keys) or any(k not in INVENTORY for k in keys):
        raise ValueError('CORE_SOURCE_KEYS contains an unknown or duplicate approved source key')
    return keys
