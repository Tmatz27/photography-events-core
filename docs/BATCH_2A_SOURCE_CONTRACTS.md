# Batch 2A: hydrology and California national park publications

Starting main/origin: `87fef36dcd8c8685952dc6483134887d6f2ba453`.
The operator reports a healthy Unraid installation: 62 iNaturalist raw identities,
172 NWS raw identities/482 normalized assertions, and valid empty WFIGS snapshots.
These are operator receipts; development does not connect to that database.

This batch adds ingestion only. No biological analysis, cross-source inference,
photographic scoring, HA changes, opportunity publication, notification or release.
The existing 81 inventory keys remain intact. `cdec` is a nonpolling family.

## Verified interfaces and scientific contracts

| Key | Official interface | Meaning, native units and time | History and correction limits |
| --- | --- | --- | --- |
| `usgs_water` | [USGS OGC documentation](https://api.waterdata.usgs.gov/docs/ogcapi/), `/ogcapi/v1/collections/continuous/items` | 00060 discharge `ft^3/s`; 00065 gauge height `ft`; exact decimal value strings, monitoring location, series, valid time, last_modified, approval/qualifier/method and provider point | Explicit finite windows and scoped next links; series+valid time identity; native modification fences; provisional values may change. No deletion endpoint is assumed. |
| `cdec_river` | [CDEC public data request](https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet) | Native sensors 1 stage `FEET` and 20 flow `CFS`; **E event duration** for POH, not an invented hourly product | Station/sensor/duration/scheduled time identity; overlapping refresh and independent history; native observation time and dataFlag retained. No modification time is supplied. |
| `cdec_rainfall` | Same official JSON servlet | Sensors 2 accumulated and 45 incremental precipitation, `INCHES`, D duration; these are distinct quantities, not automatically summed | Daily overlap; accumulation resets are native values, not manufactured rain increments. Missing values are explicit withdrawals, not zero rainfall. |
| `cdec_snow` | Same official JSON servlet | Sensors 3 snow water content, 18 depth, 82 adjusted snow water content, native `INCHES`, D duration; no conversion of water equivalent into depth | Preserve source flag, sensor and duration. Missing depth remains missing even when SWE is available. No claim of fresh snowfall follows from snowpack. |
| `nwps` | [Official OpenAPI](https://api.water.noaa.gov/nwps/v1/docs/swagger.json), `/gauges/{id}` and `/gauges/{id}/stageflow` | Station metadata/flood categories, observed stage/flow and separately issued forecast stage/flow; `ft`, `kcfs` or `cfs` remain native; validTime/generatedTime/issuedTime separate | API supplied about 30 days of observations in the investigated gauge. Current polling uses bounded overlapping slices; forecast identity includes issue cycle. Future forecast times never become measured observations. No unsupported archive query is invented. |
| `nps` | [Official NPS developer resources](https://www.nps.gov/subjects/developer/index.htm), `/api/v1/alerts` and `/api/v1/parks` | Official alerts/categories and park operating hours, weather/directions, entrance fee and linked planning information as versioned publications/references | Strict total/start/limit, unique IDs and all requested parks verified. Missing native timestamps remain NULL. Complete endpoint membership is versioned, including genuinely empty alerts; absence means not in this feed, not a proven deletion or open route. |

Government data attribution/provisional qualification remains in each payload and
assertion. [USGS](https://api.waterdata.usgs.gov/ogcapi/v0/?f=html) identifies its
data as public-domain US Government work. [DWR conditions](https://water.ca.gov/CNRAHome/Conditions-of-Use)
generally permit copying State-created data, with third-party material exceptions.
NPS API use requires a key; linked image credits/rights remain native metadata,
and no images or third-party media are downloaded. No restricted scraping is used.
NOAA metadata attribution and USGS gauge identifiers are retained: a NWPS mirror
of a USGS gauge is **not independent confirmation**.

CDEC `date` (scheduled slot) and `obsDate` are retained verbatim and interpreted as
fixed Pacific Standard Time, UTC−08:00, rather than adding summer daylight time.
Future placeholders and rows outside the requested interval are
counted as skipped. Real future measurements are rejected at persistence.
CDEC's JSON data endpoint does not supply station geometry; it remains unknown
rather than borrowing another agency's coordinates or inventing a catchment.

## Two geographic scopes

The configurable allowlists are collection sites, **not driving-time claims**.
Defaults collect USGS Santa Maria-area streamflow (`USGS-11109000`) and Yosemite
Happy Isles/Pohono (`USGS-11264500`, `USGS-11266500`), CDEC Pohono `POH`, CDEC Gin
Flat `GIN` precipitation/snow, and NWPS Pohono `POHC1`. This is an initial bounded
station footprint; it is not complete statewide hydrologic coverage, does not
measure Horsetail Fall, and cannot establish six-hour travel eligibility. Station
allowlists must be expanded deliberately with documented subject/basin relevance.
Arid/coastal parks are not assigned fictitious river gauges.

NPS always retains **all nine California national parks** using eight official
API park codes: `yose`, `seki` (Sequoia AND Kings Canyon), `deva`, `jotr`, `chis`,
`pinn`, `redw`, `lavo`. Statewide planning includes the distant parks independently
of regional travel scope. Publications are not a completed month-by-month seasonal
photography planner. Island/subregion detail is retained when supplied; transport,
permits, webcams, visitor-use and scientific monitoring feeds remain explicit
future source-reconciliation work, not fabricated NPS seasonality APIs.

`CORE_COLLECTION_SCOPE_JSON` overlays the defaults; at most 8 USGS sites and 12
sites per other family, with validated identities and no configurable origins.
For example, a deliberately smaller historical interval can be selected without
changing the NPS scope:

```dotenv
CORE_COLLECTION_SCOPE_JSON={"history_start":"2026-01-01","history_end":"2026-10-01"}
CORE_SOURCE_HISTORY=true
```

The default `history_end` is `recent`, a moving boundary six hours before the poll;
the default start is 2026-01-01. A fixed configured end is exclusive for USGS;
provider-inclusive boundaries/overlap are deduplicated. Changing scope hashes
restarts bounded progress for that scope; it never deletes previously stored data.

## Persistence, scheduling and recovery

Migration `0010` adds `environmental_assertions` because the accepted biological
table cannot honestly represent exact physical quantities, forecast issue cycles,
or publications with unknown observation time. Each revision has native numeric
text plus PostgreSQL NUMERIC, unit, evidence kind, valid/issued/native update and
collection times, quality, provider point, native payload and provenance. Run-level
`native_evidence_asof` is separate from `provider_updated_at`: CDEC's native
modification time stays NULL while freshness uses its actual measurement time.
There is one current revision per raw identity; prior revisions stay queryable.
Nothing is inserted into biological `normalized_observations` for these sources.

Current polls use existing SourceContract/Client/ownership/scheduler/persistence.
An initial six-hour slice is followed by a persisted incremental frontier with a
one-hour correction overlap. Restart catch-up proceeds in bounded day slices;
receipt clocks never skip an uncollected gap. CDEC daily feeds additionally overlap
two days. NWPS's bounded current series and forecast cycle are retained as received.

USGS/CDEC/NWPS history workers have independent `*_history` leases, backoff, quota,
checkpoint and hourly cadence. One day at one station is collected per attempt,
then station/time progress advances only after complete persistence. They share
the **same underlying raw identities** with current workers, preventing duplicated
observations. Per-record native modification/poll fences serialize revisions;
failed/cancelled/partial polls leave their frontier unchanged. Unknown native
modification times are not replaced by receipt times. Older corrections outside
ongoing overlap require an explicit bounded historical re-verification.
NWPS history starts within its accessible rolling observed series (29-day safety
margin inside the investigated approximately 30-day response), checkpoints daily
slices, and never requests an invented historical archive or reclassifies forecasts.

All six contracts use 1.1-second request spacing, 300 daily reserved requests
(NPS 150, six-hour alert polls and weekly planning-reference refresh), bounded pages and the existing HTTP size/time limits.
USGS unauthenticated access is used at a conservative rate; higher limits are not
assumed. Existing Retry-After, crash reservation and J1 deferral behavior remain.
The only backoff change allows an explicit contract for an internal history key;
deadline/failure/lease algorithms are unchanged. Missing NPS credentials disable
its scheduler task while keeping its registry/diagnostics entry visible.

Normalized numerical/reference revision history and provenance are retained
long-term, including structured park hours/context and NWPS flood thresholds in
`metadata.reference_content` and native snapshot membership. Gauge height remains
local gauge stage, not an invented above-sea-level elevation. Raw JSON blobs are pruned after 90 days only through the existing
opt-in bounded sweep; required source-run provenance is protected. The installed
`CORE_RETENTION_ENABLED=false` setting is preserved.
NPS collection membership uses a separate identity namespace and is explicitly
transport metadata; storing it does not inflate received/accepted/unique provider
record counts or create an independent observation.

## Verification and blockers

`tools/verify_batch2a_live.py --database --history` refuses any DB whose name does
not end in `_test`. It performs real upstream requests through the existing
owned collector and verifies stored native values/units/types and checkpoint
receipts. The tool never writes Unraid. Without `--database`, it records only
genuine network/parser evidence and explicitly marks persistence unverified.
Deterministic test records are separate and never counted as live evidence.

The user explicitly chose to keep **NPS live verification pending** rather than
provide `CORE_NPS_API_KEY` to CI. Its implemented parser, headers, failure,
pagination and publication persistence tests do not establish real NPS collection.
Installed verification of these new adapters also requires separate approval and
a reviewed release; no stable release/image is published by this batch.
