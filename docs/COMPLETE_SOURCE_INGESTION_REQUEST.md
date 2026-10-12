# PHOTOGRAPHY EVENTS CORE — COMPLETE SOURCE INTEGRATION

Repository:
https://github.com/Tmatz27/photography-events-core

Environment:
- Unraid Docker Compose
- PostgreSQL 18 / PostGIS 3.6
- Core service at 192.168.1.132:8099
- Existing Core API v1
- Existing accepted M1/M2/M3A architecture

## Decision

The user has explicitly authorized integrating ALL previously researched Gemini source families and restoring the useful providers from the retired Home Assistant v0.16.1 implementation.

STOP creating new source-discovery plans. The source inventory and research already exist.

This is now an engineering implementation program.

Retrieve the existing research and source contracts from the project materials. If the Gemini handoff is not accessible in your environment, request that specific handoff rather than restarting research.

The old HA repository is available as a reference for existing adapters, source URLs, authentication, parsers and evidence handling:

https://github.com/Tmatz27/Home-assistant-photography-events

Do not reactivate the HA intelligence engine. All provider collection moves to Core.

## Full approved scope

### Existing live Core sources
- iNaturalist
- NWS alerts and forecast context
- NIFC/WFIGS wildfire perimeters

Preserve their accepted contracts and operational behavior.

### Wildlife and migration
- eBird notable observations
- eBird species observations
- BirdCast/NEXRAD migration intelligence
- USFWS refuge counts and published migration reports
- Condor Express operator reports
- Supported wildlife field reports

### Marine and coastal
- NOAA NDBC measured offshore conditions
- CDIP nearshore wave data and models
- NOAA CO-OPS tides and predictions
- SCCOOS CalHABMAP
- NOAA CoastWatch ERDDAP
- MBARI Ocean Song and permitted acoustic intelligence
- Published California King Tide dates
- CDFW grunion schedules

### Weather and atmospheric intelligence
- NWS weather and safety feeds
- Open-Meteo forecast and cloud layers
- Open-Meteo air quality
- SunsetWx Sunburst
- NOAA OVATION aurora nowcast
- GOES-18 satellite products
- HPWREN camera/weather observations

### Hydrology and geographic conditions
- USGS Water Data OGC
- CDEC
- NOAA NWPS
- NPS alerts, access and closure information
- Caltrans GIS road/access context

### Vegetation and seasonal phenomena
- Sentinel-2 vegetation observations
- Theodore Payne bloom reports
- DesertUSA bloom reports
- California Fall Color reports
- Other previously approved authoritative seasonal datasets

### Astronomy
- NASA eclipse catalogs
- Previously adopted meteor shower reference data
- Astronomical computations needed by the approved phenomena

These are one committed program scope, not optional ideas to investigate again.

Do not revive phenomena the user rejected: tarantula emergence, lady beetle aggregation, elephant-seal catastrophic molt, sailing stones or deep-space stargazing.

## Architecture

Every live provider must have:

1. A source-controlled contract
2. Its own provider adapter
3. Authentication/configuration where required
4. Scheduled collection or event-driven ingestion
5. Bounded pagination and rate limits
6. Persistent cursors and retry/backoff
7. Provider-native and observation timestamps
8. Normalization and identity/deduplication
9. PostgreSQL/PostGIS persistence where appropriate
10. Source-specific freshness and coverage
11. Explicit failure/incomplete states
12. Provenance and correction/deletion handling
13. Privacy and location protections
14. Unit and integration tests
15. Bounded live verification and health diagnostics

Reuse the accepted source scheduler, database, and pattern architecture.

Do not create a second collector framework.

Read-only static catalogs do not need artificial polling. Treat them as versioned, provenance-controlled inputs.

## Credential management

Extend Core's environment-based secret configuration for credentialed providers.

Use the existing Unraid Compose `.env` approach without printing secrets.

Generate an `.env.example` describing every configurable credential, whether it is required, and which adapter consumes it.

Never include live credentials in Git, logs, errors, API projections or test fixtures.

Providers that do not require authentication must work without a key.

Providers requiring permission, a commercial subscription, or unavailable access must be implemented honestly: configure and activate them when access exists, otherwise expose `not_configured` or `access_pending`, not a fabricated successful collection.

Do not add undocumented or unauthorized scrapers.

## Engineering sequence

Implement in bounded, independently reviewable batches, but DO NOT drop providers from the final scope.

Batch 1: Complete the existing M3C operational requirements and shared source infrastructure.

Batch 2: Hydrology, weather, safety, road/access and satellite atmospheric context.

Batch 3: Birds, wildlife and migration evidence.

Batch 4: Ocean, coastal, acoustic and tidal intelligence.

Batch 5: Vegetation, bloom, foliage, seasonal and static astronomical sources.

Batch 6: Cross-source fusion, full source diagnostics, failure recovery and end-to-end live verification.

The batching is for testability and rollback, not to defer the requested source integrations indefinitely.

For each batch, run tests, push reviewable commits, and provide a complete acceptance packet for Claude's independent review.

## Scientific boundaries

Every source must contribute evidence appropriate to what it can actually establish.

Examples:
- iNaturalist presence is not proof of animal behavior.
- BirdCast migration intensity is not proof of a mass landing at a specific refuge.
- Ocean productivity is not proof of active whale feeding.
- Forecast cloud coverage is not direct observation of photographic conditions.
- Satellite vegetation indices are not confirmed peak autumn color.
- River discharge alone does not prove a waterfall moonbow.
- Road and wildfire feeds must not be interpreted as universal safe-access clearance.

Never synthesize missing evidence.

Fixed approved destinations should use one grounded baseline driving estimate; do not reintroduce continuous dynamic routing unless separately authorized.

Protect wildlife coordinates and sensitive observation details.

## Shadow and production separation

Keep all newly collected information within the existing safe evidence/pattern architecture.

The current production `/api/v1/opportunities` path still requires fixture-era M1 sources.

Do NOT simply rename new live source keys to satisfy old M1 requirements.

Do NOT insert fake fixture records to make Home Assistant show an assessment.

Design and implement the appropriate real-source assessment integration under separate acceptance gates.

No shadow result may become an actionable production recommendation without approved ecological, destination, safety, freshness and coverage validation.

Do not claim the full photographic product is operational merely because collectors are working.

## User-facing goal

Home Assistant v0.17 is now installed and connected to Core.

The long-term goal is for Core to supply all four HA views:

- Can't Miss
- Watching
- Year Planner
- Birds

Keep the Home Assistant integration thin. All scientific analysis remains in Core.

## Deliverables

Maintain a source implementation register with these statuses:

- Not implemented
- Adapter implemented
- Credentials needed
- Live collection verified
- Persistence verified
- Evidence integration verified
- Ready for independent acceptance

No provider is considered integrated solely because a configuration variable exists or an HTTP request succeeds.

For every batch deliver:
- Changed files and commit SHA
- Provider adapters and contracts implemented
- Configuration variables required
- Database changes
- Test results
- Bounded live verification results
- Remaining provider-specific blockers
- Operational deployment instructions
- Claude independent-review handoff

No release or production promotion without separate authorization.

## Start now

Begin with a short implementation mapping against the existing Core architecture, then immediately implement Batch 1.

Do not produce another general research report, re-scope the source list, or ask whether we want to proceed.

The requirement is complete integration of the approved source ecosystem.
