# Batch 2A R1–R3 correction

Starting main and origin/main: `9ce212708cbaf11c40427ed3b36a9b9886ceaea4`.
Reviewed implementation: `83f5d3df562b082f5e447ce49753ab8f5ae6d73a`.
Scope remains the 81 approved inventory keys, ingestion only. Await independent
acceptance and explicit release approval after testing. No Unraid connection or
production data change is part of this pass.

## Source corrections

**CDEC river/rainfall/snow (R1).** A fully read, valid JSON array containing no
observations is a successful request with a `no_observations` station/window
receipt. An empty historical window advances its checkpoint after persistence;
it neither deletes older values nor claims measurements exist. Malformed rows,
bad envelopes, failed requests, request-budget exhaustion and partial persistence
block progress. Daily history excludes overlap rows outside that historical
window; current daily polling still retains its two-day overlap. Separate station
requests preserve healthy siblings after a station fails. A restart resumes the
persisted station/window, including after consecutive empty days.

**NWPS (R2).** Run receipts retain `measurement_asof` from actual observed
`validTime` and `forecast_asof` from the forecast `issuedTime`, independently.
The returned observed series can establish that the last observation is stale
even outside the current persistence slice; it is not repeatedly stored in full.
Missing/withdrawn numerical values never supply freshness. Forecast identities,
issue cycles, valid times, quantities and units are preserved. Aggregate current
health conservatively requires measurements and forecasts across all configured
stations; it uses the oldest required station/product clock, or unknown if one
is missing. New forecasts cannot renew observed conditions.

**USGS (R3).** Every configured station records attempted and successful HTTP
requests, completion, received/parsed/rejected counts, measurement availability,
native time and fixed error code. Current diagnostics distinguish `current`,
`stale`, `no_observations`, `failed`, `incomplete` and `unknown`. One station's
latest value cannot certify the others. A successful empty response remains an
operational success but aggregate evidence freshness is unknown, so source health
is STALE rather than UP. Valid siblings persist during incomplete collections.

**NPS.** Per-record scope/identity validation now isolates malformed siblings.
Rejected endpoint rows cannot certify complete membership or advance checkpoints.
Live credential verification remains pending by the user's decision; synthetic
tests are not NPS live evidence.

## Operational interpretation

The authenticated `/api/v1/debug/ingestion` response adds separate `coverage` and
`history_coverage` projections. Their station IDs are public hydrology station
identities; coordinates, raw observation IDs and secrets remain excluded.
`successful_requests` counts decoded successful HTTP requests;
`successful_stations` counts fully requested stations, even legitimately empty
ones. `measurement_values`/`forecast_values` count parsed values in the stored
slice; the native clocks can also describe the longer returned NWPS series.
`parsed` is not a claim of database acceptance; operational run counts report
accepted/rejected persistence, and persistence errors invalidate station status.

Historical workers report `history_worker_health` using run completion/progress,
not the age of archived measurements. Historical native freshness is
`not_applicable`; `history_operational.history_complete` describes backfill
completion separately. Before the first corrected receipt, station coverage is
unknown/absent; no historical station outcome is fabricated. Full backfill is
not implied by a verified slice or a green worker status.

Current source-level `native_evidence_asof` is now the conservative clock across
required stations/products. Consult separate station/product clocks for detail.
Existing J1 deferrals, lease fences, recovery reservations, cancellation and
failure backoff remain authoritative. Retry-After stops sibling requests, as
does HTTP 429; a failure at a station without a global delay can leave other
stations independently useful. No incomplete run advances its checkpoint.

## Additional review findings

1. **Quotas.** Hydrology keeps 300 reserved requests/day per existing worker and
   1.1-second spacing. Per-collection budgets are USGS `max(12, 4 × stations)`
   (two parameters plus page headroom), NWPS `2 × stations`, CDEC `stations`.
   History selects one station. The effective interval is the larger of the base
   interval and `ceil(budget × 86400 / 300)` seconds. Default scopes remain hourly;
   eight USGS stations use 9,216 seconds and twelve NWPS stations 6,912 seconds.
   The HTTP client stops before reserving/requesting beyond its collection budget;
   that incomplete window is retried without losing history. Manual requests,
   failures and history can still consume quotas; provider-wide anonymous limits
   can be lower than local limits. [USGS key documentation](https://api.waterdata.usgs.gov/docs/ogcapi/keys/)
   describes service rate-limit headers and optional access keys. This pass does
   not claim anonymous access capacity is guaranteed or raise provider quotas.
2. **Malformed siblings.** USGS, CDEC, NWPS and NPS validate individual rows within
   record isolation. Invalid envelopes/pagination still fail the collection;
   individually valid siblings survive without certifying complete progress.
3. **Daily CDEC age.** The existing 48-hour threshold is retained. Daily data can
   legitimately approach or cross it after delayed reporting. Receipt time and
   quality flags cannot refresh the native observation; beyond the threshold
   diagnostics remain stale. No freshness threshold was widened to hide lag.
4. **Precision.** Environmental HTTP decoding retains the original JSON decimal
   token for `native_value` and PostgreSQL NUMERIC, including trailing digits and
   exponent notation. Existing provider string values remain exact. Ordinary raw
   JSONB is decoded JSON, not a byte-for-byte wire archive; float-compatible
   geometry/JSON serialization does not promise original number formatting.
   Previously stored float-decoded values cannot be reconstructed retroactively;
   a later real recollection can create a retained correction. Original M1/M2
   collector decoding is unchanged. Parser/contract version is `batch2a-2`.
5. **Station identity/timezone.** Read-only authoritative metadata verification
   confirmed the following. The earlier description of 11109000 as Santa Maria
   was wrong and is corrected; the station ID/data remain unchanged.

| Station | Provider description | Published longitude, latitude |
| --- | --- | --- |
| USGS-11109000 | Santa Clara River near Piru, Ventura County | −118.73924108438321, 34.4036060154662 |
| USGS-11264500 | Merced River at Happy Isles Bridge | −119.55902427621368, 37.73130354223962 |
| USGS-11266500 | Merced River at Pohono Bridge | −119.66566666666667, 37.71627777777778 |
| CDEC GIN | Gin Flat, Merced River basin, Mariposa County | −119.774907, 37.766887 |
| CDEC POH | Merced River at Pohono Bridge near Yosemite | −119.666275, 37.716873 |
| NWPS POHC1 | Merced River at Pohono Bridge; usgsId 11266500 | −119.6662788, 37.71687138 |

Metadata receipts retain URLs, retrieval times and SHA-256 digests under this
pass's evidence directory. Sources: [USGS monitoring locations](https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/items?f=json),
[CDEC GIN](https://cdec.water.ca.gov/dynamicapp/staMeta?station_id=GIN),
[CDEC POH](https://cdec.water.ca.gov/dynamicapp/staMeta?station_id=POH),
[NWPS POHC1](https://api.water.noaa.gov/nwps/v1/gauges/POHC1).

[CDEC's own service documentation](https://cdec.water.ca.gov/dynamicapp/wsSensorData)
explicitly says dates/times/output always use Pacific Standard Time. The fixed
UTC−08:00 interpretation is retained, including summer. NWPS/USGS measurements
use their offset-bearing timestamps; their local station labels do not replace
those offsets. Published agency coordinates differ slightly at Pohono; they
remain agency-specific and are not merged or treated as independent evidence.
CDEC measurement geometry remains NULL because its data response does not supply
it. Metadata research does not prove instrument accuracy, catchment relevance,
current service at every configurable station, Horsetail Fall flow, or safe
travel. No new geographic suitability claim is made.

## Verification and acceptance

Portable and real PostGIS tests add targeted R1–R3 cases while retaining all 568
accepted test identities. The original combined CDEC wrong-station/empty test
keeps its identity; R1 replaces only its superseded empty-is-HTTP-failure
expectation with explicit truthful empty receipt/progress assertions.

`tools/verify_batch2a_live.py --database --history` exports station/window context
alongside real collection and NUMERIC persistence checks. It refuses an installed
database: only a disposable name ending in `_test` is accepted. CI runs full
PostgreSQL 18/PostGIS 3.6 tests, migrations through unchanged 0010, revision
retention, parity, original collectors, restart/restore and image-stack checks.
Exact tested commit, CI URL, test identity comparison, live per-source results,
and remaining access/freshness limitations accompany the final evidence receipt.
