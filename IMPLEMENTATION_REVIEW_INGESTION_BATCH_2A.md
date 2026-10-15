# Batch 2A independent Claude review handoff

Starting main: `87fef36dcd8c8685952dc6483134887d6f2ba453`.
Exact tested code freeze: `83f5d3df562b082f5e447ce49753ab8f5ae6d73a`.
CI: https://github.com/Tmatz27/photography-events-core/actions/runs/38688659355
Receipts: `docs/evidence/ingestion-batch-2a/receipt.json`.

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

## Verified acceptance packet

568 real PostGIS tests passed with no skips/failures/errors. The packet preserves all 501 release cases, 491 J1 cases, 471 Batch 1 cases and 446 historical H1 cases. Ruff/compile, 15 fixture parity recaptures, nine pipeline cases, 18,000 evaluator comparisons/zero mismatches, fresh/repeated migrations through 0010, restart/failure/restore and image-only existing-volume preservation passed.

Five hydrology adapters have real numerical values in PostgreSQL for current and historical slices. Full archive backfill is not claimed complete. NPS remains credential-pending by the user's explicit decision; deterministic API/persistence tests are not presented as genuine NPS data. No installed database was changed and no release/image published. Review all code from the starting receipt through this freeze; subsequent evidence-only commits do not change the tested implementation.
