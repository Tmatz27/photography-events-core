# Batch 2A R1–R3 independent Claude review

Review repository `Tmatz27/photography-events-core` read-only. Starting main:
`9ce212708cbaf11c40427ed3b36a9b9886ceaea4`. Prior accepted implementation: `83f5d3df562b082f5e447ce49753ab8f5ae6d73a`.
Corrected implementation freeze: `10bde5f0dcb57821f36a971af9e3dc4183271202`. Later evidence-only commits do not
change the implementation. Review the entire diff from starting main to this freeze.

CI: https://github.com/Tmatz27/photography-events-core/actions/runs/39624699610
Evidence: `docs/evidence/ingestion-batch-2a-corrections/receipt.json`.
Source semantics/limitations: `docs/BATCH_2A_CORRECTIONS.md`.
Changed files: the receipt's `correction_files` list.
Exact 43 new test identities: `docs/evidence/ingestion-batch-2a-corrections/new-test-identities.json`.

611 tests passed against real PostgreSQL 18/PostGIS 3.6, zero skips/failures/errors.
All 568 Batch 2A, 501 release, 491 J1, 471 Batch 1 and 446 H1 identities remain.
Portable: 253 passed, 358 expected DB skips. Ruff/compilation, full legacy parity
(18,000 comparisons, zero mismatches), fresh/repeated migrations through unchanged
0010, revision retention, restart/restore, operational failure injection and
image-only existing-volume validation are in the complete CI packet.

Please independently reproduce and focus on:

1. R1: valid empty CDEC station-days progress only after complete persistence.
   Consecutive empties, later data, partial failures, malformed/truncated envelopes,
   restart, same historical slice retry, and no deletion by absence. Current
   siblings retain valid records/status. Daily history excludes overlap outside
   the requested window while current polling retains its daily overlap.
2. R2: observed valid time and forecast issued time remain separate, including
   a stale observed series outside the stored current slice. Verify all four
   freshness combinations, forecast cycle/valid time/native values, conservative
   source-level health, and history worker progress independent of archive age.
3. R3: successful HTTP requests versus actual numerical observations per station;
   one healthy station cannot conceal silent/failed stations. Review aggregate
   coverage, current/history separation, recovery and valid sibling persistence.
4. Additional findings: scope-sized request budgets/effective intervals must fit
   existing quotas; reject malformed siblings without losing valid ones; daily
   48-hour freshness remains honest; real JSON decimal tokens survive as native
   text/NUMERIC; old float loss is not retroactively reconstructed. Validate
   official station/timezone receipts and the corrected Piru station description.
5. Existing J1 deferral/recovery, lease/revision/order fences, Retry-After,
   cancellation, privacy and source identity. Ignored out-of-order runs cannot
   certify station coverage or replace a newer checkpoint. The ownership change
   only selects the effective interval; scheduler algorithms are unchanged.
6. Genuine network/PostGIS evidence versus deterministic synthetic cases. Inspect
   every source's live gates and native clocks; success of a request does not imply
   all stations have fresh observations. NPS remains credential-pending by user
   choice. Full backfill and installed collection are not claimed complete.

The legacy combined CDEC wrong-station/empty test retains its identity. R1 replaces
its obsolete empty-is-HTTP-failure expectation with stronger explicit empty
receipt/progress assertions; the malformed-station failure remains required.

Return PASS, PASS WITH REQUIRED FIXES, or FAIL with severity, reproducible findings
and exact lines. Do not implement Batch 2B, redesign intelligence, change Home
Assistant, publish a release/image, or connect to the installed Unraid database.
Independent acceptance and the user's explicit release approval are still required.

## Genuine live results at the tested freeze

| Source | Current assertions / numerical values | History assertions / numerical values |
| --- | --- | --- |
| USGS | 136 / 136 | 142 / 142 |
| CDEC river | 40 / 40 | 194 / 194 |
| CDEC rainfall | 4 / 1 | 2 / 2 |
| CDEC snow | 6 / 4 | 3 / 3 |
| NWPS | 283 / 282 | 177 / 176 |
| NPS | Credential-pending, zero HTTP requests | No accessible authenticated verification |

All five hydrology datasets have real current/history collection and persistence
receipts. All three configured USGS stations returned current measurements in
this particular probe; silent/stale/failure combinations are tested separately
with explicit synthetic regressions. NWPS returned a current observation at
15:00 UTC and a separate forecast issue at 14:16 UTC on 2026-10-21. Daily CDEC
rainfall's last actual numerical measurement is 2026-10-20 00:00 PST; its other
three current-slice assertions are withdrawals, not zero rainfall. CDEC snow's
two missing values remain withdrawals, not measured snow depth.

The existing iNaturalist and NWS collectors returned real records and persisted
them. WFIGS returned a verified complete empty snapshot: its run receipt and
freshness are verified, with zero incident assertions and `persistence_verified`
false for incident rows. No incident was invented to make that gate green.
Full source and station native clocks, units, counts, checkpoints and database
gates are retained in `live-summary.json`, `batch2a-live.json` and
`ingestion-live.json` under this correction's evidence directory. The live
archive probes verify finite slices, not completion of the entire backfill.
