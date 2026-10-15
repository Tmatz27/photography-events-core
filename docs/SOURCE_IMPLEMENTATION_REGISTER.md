# Complete source ingestion program and completion matrix

The development priority is data ingestion first. The full supplied provider
inventory is committed scope; batches are review boundaries, never removals.
Authority: `COMPLETE_SOURCE_INGESTION_REQUEST.md` and the user's accompanying
priority change. Legacy source mapping uses frozen HA v0.16.1's
`SOURCE_VALIDATION.md`, `TRACKING.md` and adapters; current HA is read-only reference.
Rejected phenomena remain excluded. No score, phenomenon evaluator, HA view,
assessment publication, notification or release is part of this phase.

Core starting origin/main: `b14014760beee2c18d02a2b1f36756f6faee93a0`.
HA reference HEAD: `95a746cbcc3c97b95dd05774481cc13fad2c6955` (unchanged).
The user supplied the combined master inventory after the initial mapping, then
explicitly clarified ALL identified sources, including experimental interfaces.
This registry includes every named Top 20 provider, all legacy families, the
additional research recommendations and later safety/air-quality candidates.
The Top 20 rank is retained as metadata, not a cap. Distinct dataset records
remain separate even when a provider or current collector is shared. A standalone
M3C specification remains unavailable; known reliability gaps are addressed here,
without claiming conformance to an unseen document. Exact endpoints, coverage,
permissions and storage rights are validated during each adapter implementation.
No undocumented scraper or guessed commercial/private API is implemented.

## Architecture mapping and batches

Existing path: Core lifespan -> existing Scheduler -> per-provider SourceContract
and adapter -> bounded Client -> Batch/Fact -> isolated PostgreSQL persistence.
Short durable poll leases and recovery backoff precede HTTP; accepted poll/version
fences protect persistence. M1's pool, lock, deadlines and production source keys
are untouched. Native measurement/observation time, provider correction time,
collection time and cursor progress stay separate. Existing normalized revisions
and provenance remain retained; future quantity adapters must store actual units,
quality, precision and native fields rather than manufacturing biological facts.
Reference catalog imports will have explicit version/content hashes and native
provenance, without automatic polling. No second collector framework is introduced.

1. Shared collector operations and accepted existing providers: ownership/recovery,
   async request cancellation, checkpoints, privacy/correction retention, retired-ID
   refresh, indexed CAP barriers, inventory/configuration and safe diagnostics.
2. Hydrology, weather, safety, road/access and satellite atmospheric context.
3. Birds, wildlife and migration evidence; supported/permissioned report ingress.
4. Marine, coastal, acoustic and tidal sources; published planning references.
5. Vegetation, bloom, foliage, seasonal and static astronomical inputs.
6. Cross-source ingestion reconciliation, diagnostics, recovery and full live/DB
   verification. Photographic intelligence/fusion scoring remains a later gate.

Status columns are independent proof gates. "Adapter implemented" is not a live
or installed Unraid certification. Credential configuration is not collection.
No source is complete until a genuine provider payload is accepted and its
native assertions are verified in PostgreSQL. Partial good records may persist
while the source remains incomplete; a complete empty current snapshot is valid
only when its contract actually proves scoped completeness.

## Provider completion matrix

| Provider key / approved dataset | Batch/type / original rank | Adapter / schedule | Real collection | Persistence / history | Evidence integration | Independent gate | Credentials / access / legacy mapping |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `inaturalist` — iNaturalist | 1 / live / additional | Adapter implemented via `inaturalist`; 1800 s | Batch 1 real complete collection verified | 65 actual identities/assertions/receipts verified in fresh PostGIS; installed Unraid pending | Accepted safe shadow evidence only | Batch 1 review pending | No configured key; public; legacy `observations.py` |
| `nws_live_context` — NWS alerts and forecast | 1 / live / additional | Adapter implemented via `nws_live_context`; 900 s | Batch 1 real complete collection verified; native issue remains stale | 158 actual identities/assertions/receipts verified in fresh PostGIS; installed Unraid pending | Accepted safe shadow evidence only | Batch 1 review pending | No configured key; public; legacy `weather_hazards.py / conditions.py` |
| `wfigs_current` — NIFC/WFIGS current wildfire perimeters | 1 / live / additional | Adapter implemented via `wfigs_current`; 900 s | Batch 1 complete valid empty snapshot verified | Run/cursor persisted; positive-fire rows not exercised in empty live snapshot; installed Unraid pending | Accepted safe shadow evidence only | Batch 1 review pending | No configured key; public |
| `usgs_water` — USGS Water Data OGC | 2 / live / 1 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `streamflow.py` |
| `cdec` — CDEC dataset family | 2 / group / additional | Scope group; no poll | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `nwps` — NOAA NWPS | 2 / live / 17 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `nps` — NPS alerts, access and closures | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_NPS_API_KEY`; public; legacy `parks.py` |
| `caltrans` — Caltrans QuickMap/ArcGIS road and chain-control context | 2 / live / 9 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `open_meteo` — Open-Meteo forecast and cloud layers | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `conditions.py` |
| `open_meteo_air_quality` — Open-Meteo air quality | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `sunsetwx` — SunsetWx Sunburst | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_SUNSETWX_CLIENT_ID`, `CORE_SUNSETWX_CLIENT_SECRET`; subscription; legacy `sunburst.py` |
| `ovation` — NOAA OVATION aurora nowcast | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `conditions.py` |
| `goes18` — GOES-18 ABI-L2 cloud/fog products | 2 / live / 12 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `hpwren` — HPWREN dataset family | 2 / group / additional | Scope group; no poll | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; permitted interface required |
| `hpwren_cameras` — HPWREN camera images | 2 / live / 7 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; image/archive rights and approved camera allowlist required |
| `hpwren_weather` — HPWREN weather station observations | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; permitted station interface required |
| `ebird_notable` — eBird notable observations | 3 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_EBIRD_API_KEY`; public; legacy `birds.py` |
| `ebird_species` — eBird species observations | 3 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_EBIRD_API_KEY`; public; legacy `birds.py` |
| `birdcast` — BirdCast migration products | 3 / live / 5 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved data interface/storage rights required |
| `nexrad` — Independently processed NEXRAD weather radar | 3 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved product/pipeline required |
| `usfws_counts` — USFWS refuge counts | 3 / live / 14 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved reports/interface required |
| `usfws_reports` — USFWS published migration reports | 3 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved reports/interface required |
| `condor_express` — Condor Express operator reports | 3 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `field_reports.py` |
| `field_reports` — Supported wildlife field reports | 3 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; trusted ingress; subscriptions/permission required; legacy `email_reports.py / field_reports.py` |
| `email_reports` — Legacy subscribed email report ingress | 3 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_IMAP_HOST`, `CORE_IMAP_USERNAME`, `CORE_IMAP_PASSWORD`; user subscription; legacy `email_reports.py` |
| `ndbc` — NOAA NDBC measured offshore conditions | 4 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `waves.py` |
| `cdip_models` — CDIP nearshore wave models | 4 / live / 11 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `waves.py` |
| `cdip_measured` — CDIP measured waves | 4 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `coops` — NOAA CO-OPS dataset family | 4 / group / additional | Scope group; no poll | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `grunion.py / conditions.py` |
| `coops_predictions` — NOAA CO-OPS station tide/high-low predictions | 4 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `grunion.py / conditions.py` |
| `coops_water_level` — NOAA CO-OPS measured station water levels | 4 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `calhabmap` — SCCOOS CalHABMAP | 4 / live / 6 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `coastwatch_sst` — NOAA CoastWatch ERDDAP sea surface temperature | 4 / live / 2 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `coastwatch_chlorophyll` — NOAA CoastWatch ERDDAP chlorophyll | 4 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `coastwatch_upwelling` — NOAA CoastWatch ERDDAP upwelling context | 4 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `mbari_ocean_song` — MBARI Ocean Song / permitted acoustics | 4 / live / 8 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_MBARI_API_TOKEN`; access_pending; approved interface/permission required |
| `king_tides` — Published California King Tide dates | 4 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `events.py` |
| `grunion` — CDFW grunion schedules | 4 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `grunion.py` |
| `sentinel2` — Sentinel-2 vegetation dataset family | 5 / group / 3 | Scope group; no poll | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_COPERNICUS_CLIENT_ID`, `CORE_COPERNICUS_CLIENT_SECRET`; approved access path required |
| `sentinel2_ndvi` — Sentinel-2 NDVI vegetation observations | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_COPERNICUS_CLIENT_ID`, `CORE_COPERNICUS_CLIENT_SECRET`; approved access path required |
| `sentinel2_evi` — Sentinel-2 EVI vegetation observations | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_COPERNICUS_CLIENT_ID`, `CORE_COPERNICUS_CLIENT_SECRET`; approved access path required |
| `theodore_payne` — Theodore Payne bloom reports | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; permitted published report interface required; legacy `field_reports.py` |
| `desertusa` — DesertUSA bloom reports | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; permitted published report interface required; legacy `field_reports.py` |
| `california_fall_color` — California Fall Color reports | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; permitted published report interface required; legacy `field_reports.py` |
| `seasonal_references` — Other previously approved authoritative seasonal datasets | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; Gemini handoff needed to enumerate; scope remains committed |
| `nasa_eclipses` — NASA eclipse catalogs and path tables | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `eclipse_catalog.json / tools/import_eclipses.py` |
| `meteor_reference` — Previously adopted meteor shower reference data | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `events.py / astronomy.py` |
| `astronomical_inputs` — Approved astronomical computation inputs | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `astronomy.py / lunar.py` |
| `legacy_seasonal_references` — Legacy authoritative seasonal references (USFWS, Xerces/State Parks, monitored seal colonies) | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `SOURCE_VALIDATION.md / curation.py` |
| `nws_active_alerts` — NWS Active Alerts | 1 / live / 4 | Adapter implemented via `nws_live_context`; 900 s | Shared accepted NWS collector verified; independent dataset gate pending | Combined NWS collector persistence verified; separate dataset counts/health pending | Accepted safe shadow evidence only | Batch 1 review pending | No configured key; public |
| `nws_hourly_forecast` — NWS hourly forecast context | 1 / live / additional | Adapter implemented via `nws_live_context`; 900 s | Shared accepted NWS collector verified; independent dataset gate pending | Combined NWS collector persistence verified; separate dataset counts/health pending | Accepted safe shadow evidence only | Batch 1 review pending | No configured key; public |
| `nws_gridpoints` — NWS Gridpoints forecast fields | 2 / live / 13 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `nws_forecast_discussions` — NWS forecast discussions | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `inaturalist_plants` — iNaturalist plant observations | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `ebird_checklists` — eBird checklist reports and counts | 3 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_EBIRD_API_KEY`; public |
| `motus` — Motus Wildlife Tracking Network | 3 / live / 16 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; permission/credential/license and machine interface pending |
| `whale_alert` — Whale Alert reported sightings | 3 / live / 15 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; machine interface/permission/archive rights pending |
| `whale_safe` — Whale Safe | 3 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; provider API inquiry/permission/archive rights pending |
| `audubon_reports` — Local Audubon reports | 3 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved feeds/publisher permissions required |
| `ranger_reports` — Approved park ranger/blog reports | 3 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved feeds/archive rights required |
| `harbor_operator_reports` — Public harbor/operator reports | 4 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved feeds/archive rights required |
| `approved_rss` — Other approved RSS feeds | 3 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved feed allowlist/archive rights required |
| `cdec_river` — CDEC river gauges | 2 / live / 10 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `cdec_rainfall` — CDEC rainfall sensors | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `cdec_snow` — CDEC snow sensors/snowpack | 2 / live / 20 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `cdec_soil_moisture` — CDEC soil moisture sensors | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `goes_glm` — GOES GLM lightning observations | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `county_air_quality` — County Air Quality District observations | 2 / live / 19 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved district feeds/archive rights required |
| `purpleair` — PurpleAir | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | `CORE_PURPLEAIR_API_KEY`; credential/plan/archive rights required |
| `blm` — BLM ArcGIS land/access restrictions | 2 / live / 18 | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `state_parks_gis` — California State Parks GIS | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `usfs_access` — USFS roads/closures/access data | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `beach_restrictions` — Local municipal/county beach restrictions | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved local agency datasets/archive rights required |
| `cal_fire` — CAL FIRE incident information | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `watchduty` — WatchDuty | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; authorized machine interface/permission/archive rights pending |
| `landsat` — Landsat vegetation observations/indices | 5 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |
| `xerces_monarch` — Xerces monarch counts and references | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; published count dataset/archive rights required |
| `state_parks_monarch` — State Parks monarch reports | 5 / event / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; approved published reports required |
| `elephant_seal_reports` — Official elephant-seal seasonal/breeding reports | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `SOURCE_VALIDATION.md` |
| `harbor_seal_reports` — Official harbor-seal seasonal reports | 5 / reference / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public; legacy `SOURCE_VALIDATION.md` |
| `noaa_solar` — NOAA solar/space-weather observations | 2 / live / additional | Not implemented; schedule pending contract | Not verified | Not verified; normalized history retained after licensed implementation | Deferred separate intelligence gate | Not ready | No configured key; public |

## Credential and access gates

All current public collectors remain keyless. `.env.example` lists every current
credential slot and its future adapter consumer, and Compose passes only the
application configuration. Settings keeps credential values out of repr; errors,
inventory diagnostics and evidence contain variable names/configured booleans,
never secret values. MBARI/Copernicus access slots are provisional until the
approved handoff and permissioned interface establish their actual requirements.
They are not speculative authenticated clients. A requested unimplemented source
stays `not_implemented`, with credential availability independently visible.
Missing access never becomes a successful empty collection.

## Measurement organization, redundancy and provenance

`src/pec/sources/inventory.py` is the permanent machine-readable registry. Every
entry has measurement/evidence kind, original rank (when relevant), batch, static
versus live/event/group type, credentials/access, native lineage and retention/
historical-coverage status. Live diagnostics add the actual current collector
schedule, native/receipt timestamps, received/accepted/rejected outcomes through
the existing contract endpoint, backoff and PostgreSQL identity/assertion counts.
Unimplemented entries keep unknown schedules/coverage; their contracts cannot
be invented from a research ranking. Scope groups are not artificial polls.

| Measurement | Primary / alternate observation candidates | Complementary context; not equivalent replacement |
| --- | --- | --- |
| Snow accumulation | CDEC snow stations; HPWREN camera records offer visual evidence | NWS/Open-Meteo snowfall is forecast; camera labels are not fabricated |
| Bird migration | BirdCast products and independently processed NEXRAD | Both may use the same radar; eBird/USFWS/Motus observe different populations/coverage |
| Whale presence | Dated visual/operator reports and Whale Alert reports | MBARI acoustics and CoastWatch ocean products establish different facts; Whale Safe lineage may overlap |
| River/waterfall conditions | USGS/CDEC gauge measurements where site/variable/time match | NWPS/NWS forecasts cannot replace measured discharge or prove a moonbow |
| Ocean waves | NDBC and CDIP measured series with honest station/basis | CDIP nearshore models remain models; offshore waves do not certify coastal access |
| Cloud/fog | GOES imagery/products and HPWREN camera/weather observations | NWS/Open-Meteo forecasts are complementary, not observed visibility |
| Wildfire/access | NWS alerts, WFIGS perimeters, official CAL FIRE and road/agency restrictions | WatchDuty/reporting overlap is retained; no absence means universal safe access |
| Bloom/foliage | Dated field/seasonal reports and public plant observations | Sentinel-2/Landsat indices and CDEC soil moisture are complementary environmental records |
| Bioluminescence | Approved dated nighttime field reports | CalHABMAP/ocean/lunar conditions are context, never synthesized glow observations |

All accessible complementary and alternate providers remain scheduled for
integration; a successful primary never disables the others. Measurement/site,
units, valid time, precision, lineage and license must match before any future
comparison could regard records as equivalent. eBird API views of one checklist,
iNaturalist taxon views of one UUID, syndicated reports and multiple NEXRAD-derived
products do not create independent confirmation. No scientific fusion runs here.

Current accepted iNaturalist coverage remains the bear/monarch coastal slice,
not all requested wildlife/plant taxa. The accepted NWS collector combines CAP
and hourly temperature context; the new dataset entries explicitly share that
collector and its operational counters. Full grid fields/discussions and independent
dataset-level lifecycle/health are pending their ingestion batch. Broader future
coverage and these additional measurements are not claimed by existing adapters.

## Batch 1 operational verification and blockers

New real schema migration 0009 adds per-source lease ownership/checkpoints and
an indexed explicit CAP barrier table; migrations 0001–0008 remain byte-identical.
No measurement/history purge is introduced. Opt-in hourly retention runs one
bounded 500-row sweep. For live source blobs the cutoff is last verified receipt,
preserving a freshly received fire despite an old geometry edit. Native times and
normalized history are never rewritten. CAP reference barriers and their provenance
survive payload pruning; previously pruned reference bodies cannot be reconstructed
unless a retained per-record fence or approved provider history supplies them.

Retired iNaturalist numeric IDs are refreshed from the latest retained assertion,
with the existing validity envelope, 200-ID page cap and persistent rotation.
Reappearance never lowers privacy. Old IDs outside that bounded relevance window
are not rediscovered indefinitely. Explicit CAP fences use an indexed identity
lookup instead of a raw-body scan; original/update/cancel ordering must remain green.

`/api/v1/debug/ingestion` is bearer-protected and typed; it exposes scope/status,
credential availability, timing/backoff/lease and aggregate history counts. It
exposes no cursor body, lease token, provider identifier, raw geometry or secret.
The existing source-contract and calibration diagnostics retain their accepted semantics.

Live verification tool: `tools/verify_ingestion_live.py`. It invokes actual
approved adapters, persists through the same quota/version/privacy path, and
verifies fresh database receipts/native timestamps/digests. It never imports
fixture observations or assessments. Outages, HTTP denial, schema drift, partial
pages and cancellation remain failed/incomplete in the report. CI verification
uses a disposable *_test database. Installed Unraid verification requires the
operator mode and an authenticated approved transport to the actual host.

This environment has no local Docker/PostGIS. Real DB coverage runs in Docker CI.
A strict noninteractive SSH check to 192.168.1.132 failed because no verified host
key is configured. No host-trust check was bypassed and no server was modified.
Unraid installation/collection/persistence remains unverified from this environment.
No production secrets are present in the repository; remaining provider credential
and permission requirements are recorded above. The entire phase is NOT complete.
Batch 1 cannot claim conformance to an unseen standalone M3C specification.

## Latest Batch 1 receipt

See `IMPLEMENTATION_REVIEW_INGESTION_BATCH_1.md` and `docs/evidence/ingestion-batch-1/`.
471 real PostGIS tests passed (all 446 H1 cases plus 25). Actual provider data:
65 iNaturalist and 158 NWS identities/assertions/receipts in a fresh fixture-free
live test database; WFIGS supplied a valid empty snapshot and persisted run/cursor.
NWS native issue freshness remains stale. Installed Unraid verification is
operator-pending, and no remaining adapter/access gate is marked complete.

## Batch 2A continuation

See `BATCH_2A_SOURCE_CONTRACTS.md` and `IMPLEMENTATION_REVIEW_INGESTION_BATCH_2A.md`.
All 81 keys remain; `cdec` is nonpolling. Six new adapters are implemented;
implementation is not a source-completion certificate. The user reports the new
installed Unraid is healthy with 62 iNaturalist raw records, 172 NWS raw records/
482 historical normalized assertions and successful empty WFIGS snapshots. This
supersedes the old operator-pending installed status for those three collectors
as user-provided evidence; development did not inspect or write that database.
Batch 1/J1 acceptance is supplied by the user's current task. Older matrix entries
and receipts remain historical evidence rather than fresh installed certification.

Batch 2A NPS real collection is credential-pending by explicit user choice. All
new installed-source verification, Claude acceptance, expanded station footprints
and remaining providers stay open. No stable release is authorized by this batch.
