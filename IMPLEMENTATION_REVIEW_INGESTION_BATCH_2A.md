# Batch 2A independent Claude review handoff

Starting main: `87fef36dcd8c8685952dc6483134887d6f2ba453`.
Exact tested candidate, workflow and receipts will be recorded after full CI.

Review USGS OGC, CDEC river/rain/snow, NOAA NWPS and NPS ingestion only. The source
contracts, licensing links, actual coverage and limitations are in
`docs/BATCH_2A_SOURCE_CONTRACTS.md`. The entire 81-key inventory remains committed.
No HA, engine, production publication, release, or installed Unraid mutation is
part of this delivery. The installed three collectors are preserved.

Focus review on:

1. Native decimal values/units/station identity; observed vs forecast vs reference
   semantics, fixed CDEC PST, missing/quality flags, unknown native timestamps.
2. Migration 0009→0010, revision/provenance retention, PostGIS point validation,
   same identity shared by current/history workers, and revision/lease race fences.
3. Scope restrictions and pagination, no untrusted origins/secret URLs, honest
   empty/failed/partial/stale outcomes, all nine NPS parks through eight codes.
4. Independent historical and current checkpoints, bounded requests/quotas,
   Retry-After/cancellation/restart, and unchanged J1 scheduling algorithms.
5. Genuine disposable-network/DB receipts versus synthetic tests. NPS real
   collection is explicitly credential-blocked by user choice; CDEC depth may be
   missing even when SWE exists. No current hydrologic footprint is called
   statewide coverage, travel eligibility, Horsetail flow or photographic proof.
6. Full previous test identities, legacy fixtures and 18,000 evaluator comparisons,
   migrations/restart/restore and image-only deployment validation.

Please return PASS, PASS WITH REQUIRED FIXES, or FAIL with reproducible findings,
priorities and exact affected lines. Do not redesign accepted M1/M2/J1 components
or implement the remaining Batch 2 sources. Stable publication still requires the
user's explicit approval after independent review.
