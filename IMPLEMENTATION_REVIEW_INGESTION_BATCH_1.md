# Complete multi-source ingestion — Batch 1 independent Claude review handoff

## Scope and authority

The user changed development priority to ingestion and persistence first, then
supplied the combined master inventory and explicitly required ALL identified
sources, including experimental and permission-dependent interfaces. The
original Top 20 ranking is metadata, not a cap. `docs/SOURCE_IMPLEMENTATION_REGISTER.md`
and `src/pec/sources/inventory.py` retain 81 source/dataset/family/reference entries,
including distinct NWS, CDEC, CDIP, CoastWatch and vegetation inputs, all legacy
providers, WFIGS, CAL FIRE, WatchDuty, PurpleAir, Whale Safe and official seasonal
references. Group/placeholder entries are scope commitments, not invented APIs.

Batch 1 builds shared operational safeguards around the accepted three public
collectors. It does not implement or certify remaining provider/dataset/group
entries merely by naming them. No scoring, new phenomenon evaluation, source
fusion, HA presentation, automatic M2 recomputation or production publication
was added. The standalone M3C specification is still unavailable; no claim of
complete conformance to that unseen document is made.

Core starting origin/main: `b14014760beee2c18d02a2b1f36756f6faee93a0`.
HA read-only reference HEAD: `95a746cbcc3c97b95dd05774481cc13fad2c6955`.
Frozen legacy adapter/register reference: HA tag `v0.16.1`.
Main-only commits; no release, production notification or production promotion.

## Implementation mapping

The existing Scheduler still owns automatic collection. Core lifespan selects
implemented contracts from the full requested inventory; unimplemented sources
remain visible and never generate successful empty runs. Existing SourceContract,
Client, Batch/Fact, raw identity, normalized revisions and source_runs remain the
ingestion path. Database mutations continue through the isolated shadow pool.
M1 pool/lock/deadlines, source keys and production API semantics remain unchanged.

Migration 0009 is required for the real schema changes below. Migrations
0001–0008 are byte-identical. The explicit head/version assertions now expect
0009; the additional authenticated diagnostic path makes ten API routes. These
are expected assertion changes, not removed baseline tests.

### Durable ownership and restart recovery

`sources/ownership.py` claims one short per-source lease using a locked poll-state
row. The lease has a random token and bounded expiry (poll timeout + isolated DB
budget + cleanup allowance). It stores conservative recovery backoff before HTTP.
Daily request reservations remain durable, with accepted existing spacing/quotas.
No connection or M1 publication lock is held over network work. A failed process
cannot reset the interval on every restart; normal completion resumes the existing
Scheduler's persistent success/failure/Retry-After policy.

Persistence checks an optional ownership token/expiry while holding the source
state row. An expired or replaced worker cannot renew/replace/retire current
assertions, advance native cursor/checkpoint or certify an absence snapshot. The
accepted F2 rule still permits only protection increases from out-of-order facts;
an expired worker cannot lower privacy or revive evidence. It records
a truthful failed attempt. Cleanup only releases its own token; another owner's
lease cannot be cleared. Existing explicit test/manual persistence without a lease
is preserved; the automatic production collector path always uses ownership.

New bounded JSON checkpoints are committed only after a fully readable, ordered,
complete poll. Incomplete, stale, expired or oversized checkpoint attempts cannot
advance them. Native timestamps never become retrieval timestamps or cursor time.
The current accepted collectors keep their existing typed cursor/rotation columns;
provider-specific new checkpoints are available to the later adapters.

### HTTP cancellation and failures

The runtime now includes the already pinned/tested aiohttp dependency. It replaces
the blocking urllib worker thread with one bounded session/connector per collector
attempt, streaming decoded bodies with a 16 MiB maximum, 20-second total request,
10-second connection/read budgets, HTTPS origin validation and redirects disabled.
Sessions and sockets close when collection ends or is cancelled. Credentials may
be passed in request headers without being saved/logged. Provider error bodies,
exception strings and raw URLs are never diagnostic output.

Existing offline transport injection remains supported. Unexpected adapter errors
record fixed-code failed attempts. Cancellation records failure and propagates;
it is never treated as a successful empty feed. Local real-socket tests exercise
stream cancellation, oversize bodies, malformed JSON, redirects and Retry-After.
Implementation reference: [aiohttp client documentation](https://docs.aiohttp.org/en/stable/client_quickstart.html).

### G2 retired-ID refresh and G3 CAP barriers

The iNaturalist known-ID refresh now uses the latest retained assertion, including
retired recent IDs, bounded by the existing validity envelope, 200-ID cap and
persistent rotation. A complete explicit-ID response can legitimately reinstate an
unchanged UUID without a new incremental search hit. Privacy remains monotonic.
Expired historical IDs are not rediscovered indefinitely. The old G2 test keeps
its identity and reinstatement checks but explicitly updates its known-ID selection
expectation to this authorized operational correction.

NWS explicit reference barriers are stored in an indexed `(source_id,external_id)`
table. Migration 0009 backfills valid retained Update/Cancel bodies, excludes future
native clocks, and retains source-run provenance. Newly accepted references raise
the barrier atomically with their assertion/withdrawals. Replay admission uses one
indexed identity lookup, preserving accepted Update/Cancel ordering semantics.
Barriers survive bulk-payload retention. Already pruned historical reference bodies
cannot be reconstructed without a retained per-record fence/provider history.
The load acceptance script checks an actual indexed lookup under 100,000 retained
barriers; this is explicitly synthetic DB load, not fabricated live evidence.

### Retention, credentials and diagnostics

Optional `CORE_RETENTION_ENABLED=true` schedules one bounded 500-row sweep hourly.
Default remains false. Live bulk payloads use last verified receipt for the existing
90-day cutoff, so an old native fire edit cannot prune a freshly received body.
Normalized historical assertions, privacy/retirement provenance, linked decision
evidence and CAP reference provenance remain retained. There is no measurement
or normalized-history purge. Provider-specific storage licenses/retention must be
validated before later adapters archive their data.

Settings loads explicit environment credential slots with redacted repr. Compose
and `.env.example` document each current/provisional consumer. Credential values
never enter Git, diagnostic projections, logs or fixtures. Unverified permissioned
interfaces stay visible as access pending; a configured secret does not implement
an adapter or prove authorization. Public current providers remain keyless.

`/api/v1/debug/ingestion` is typed and bearer-protected. It reports the full scope,
measurement/evidence kind, upstream lineage, adapter/schedule, credential availability,
retention/history coverage, collector state/times/backoff/lease and aggregate persisted
identity/assertion counts. It exposes no native IDs, raw points, cursor bodies,
lease tokens or secrets. Dataset entries that share the accepted NWS collector
explicitly share its counters; separate grid/discussion adapters and independent
dataset lifecycle/health remain a Batch 2 requirement, not a false certification.

## Genuine live ingestion and installed-system gates

`tools/verify_ingestion_live.py` runs actual approved adapters and quota/persistence,
then verifies new database receipts, native update times, digests and historical
assertion counts. It never imports fixture observations or assessments. CI uses a
disposable real PostGIS database. Outages, provider denial, schema drift, incomplete
pages and cancellation remain failed/incomplete in the evidence. Partial good
records may have persistence verified while complete collection is unverified.

No local Docker/PostGIS is available. Full DB/migration/restore verification uses
CI's PostgreSQL 18 / PostGIS 3.6. Unraid host 192.168.1.132 has not been modified;
a noninteractive SSH attempt with strict checking found no trusted host key. No
host verification was bypassed. Installed Unraid polling/data verification is
pending an authenticated, trusted operator connection and independent acceptance.

## Operator deployment instructions after independent review

1. Preserve a verified database backup with the existing operator scripts.
2. Review migration 0009 and build the corrected Core image from main. Keep the
   existing private database network, restricted bind IP and secret `.env` permissions.
   Startup upgrades to head; do not modify migrations 0001–0008.
3. Preserve the installed shadow opt-in settings. For the three current collectors,
   use `CORE_PATTERNS_MODE=shadow`, `CORE_LIVE_SOURCES=true`, and
   `CORE_SOURCE_KEYS=inaturalist,wfigs_current,nws_live_context`. `all` includes pending
   inventory entries in the requested scope; only implemented contracts execute.
4. Keep unused credentials empty; enter required future credentials only in Unraid
   `.env`. MBARI/Copernicus protocol/access requirements still need validation.
5. Keep retention disabled until the raw archive/license policy is approved, or
   explicitly opt into the bounded existing sweep after backup/retention review.
6. Read authenticated `/api/v1/debug/ingestion` and source-contract diagnostics.
   Copy the approved verification tool into the runtime container and inspect
   actual installed state without a poll or cursor/lease mutation:

   ```sh
   docker cp ./tools/verify_ingestion_live.py photography-events-core:/tmp/verify_ingestion_live.py
   docker exec photography-events-core python /tmp/verify_ingestion_live.py --operator --inspect-only --output /tmp/ingestion-live.json
   docker cp photography-events-core:/tmp/ingestion-live.json ./ingestion-live-unraid.json
   ```

   Run these from the reviewed repository checkout after rebuilding/migrating
   the installed Core. The receipt contains counts/status/times/digests only;
   do not send `.env` or raw provider bodies. A manual collection attempt omits
   `--inspect-only`; it obeys ownership/next-allowed/quota state and cannot force
   a poll past those guards. The runtime image normally omits tools; the explicit
   copy above avoids assuming a test image is installed. Operator inspection
   records that this command made no network request; it verifies the actual
   collector's stored run/receipts. Native freshness may be stale beside a fresh
   successful receipt and is reported independently.
7. Verify source_runs, raw identities, native times, latest accepted receipt and
   normalized history directly in PostgreSQL. Keep all raw wildlife details private.
   An M1 incomplete opportunity response is expected without real accepted assessment
   integration; never import/rename fixtures to make HA display an assessment.

## Independent review checklist

- Confirm the complete supplied inventory is retained, including additional and
  experimental sources, and that the matrix never equates naming with integration.
- Review per-source lease/backoff races, process death, expiry/fencing, cancellation,
  disabled providers, request bounds and absence of M1 lock/pool use.
- Review G2 refresh privacy and G3 reference backfill/ordering/retention invariants.
- Verify all 446 H1 baseline case identities plus new cases pass against real PostGIS.
  Only schema/route expectations and the explicitly superseded G2 limitation change.
- Verify unchanged M1 15/15 byte parity, pipeline parity and 18,000/0 evaluator receipts;
  M2 isolation, H1 safety asymmetry and privacy remain accepted.
- Read genuine live evidence separately from synthetic load/offline fixtures. Inspect
  database receipts and truthful failed/incomplete sources; no invented observations.
- Confirm schema 0009 migration/repeat/restart/backup/restore and indexed CAP load evidence.
- Keep installed Unraid verification, credentials/permission/storage rights, remaining
  provider adapters and standalone M3C-spec reconciliation explicit pending gates.

Validation receipts and exact reviewed tip will be appended after successful CI.
The complete ingestion phase is NOT COMPLETE. This packet is a Batch 1 handoff,
not a full-product or unattended-operation acceptance.


## Verified Batch 1 freeze and acceptance receipts

Code/test/tool freeze: `ec97563956859c73254df3d409db5430f25ae6ed`. [Full PostGIS CI](https://github.com/Tmatz27/photography-events-core/actions/runs/38204670198) is green.
Artifact `11726329417`, ZIP SHA-256 `4a2025d86db84d17cb0a968dca09a777e6a86ec9208c672c9bd474ad3d87251b`, was downloaded and verified.
Evidence is committed under `docs/evidence/ingestion-batch-1/`; freeze-receipt.json
lists hashes and the exact 25 new named cases. The final documentation descendant
and final-tip CI are recorded externally in `outputs/INGESTION_BATCH_1_FINAL_RECEIPT.md`
beside the checkout, avoiding a self-referential Git commit.

**471 passed in 83.578s**, zero failures/errors/skips on
PostgreSQL 18.6 / PostGIS 3.6.4. All 446 accepted H1 case identities are preserved,
plus 25 new cases. Schema/version/route assertions and one superseded G2 known-ID
expectation changed as documented; no accepted test was deleted. Local Windows:
160 portable passed, 311 expected DB/POSIX/oracle skips. CI portable: 165 passed,
306 DB skips, followed by the complete real DB suite. Ruff/compile checks passed.

Genuine provider collection ran in a fresh, separately migrated
`photography_events_live_test` database, through owned collectors, durable quota,
accepted parsers and persistence. It contains no offline test fixtures:

| Source | Real collection | Actual database result | Native freshness |
| --- | --- | --- | --- |
| iNaturalist | Complete success; 1 request, 65 accepted, 0 rejected | Exactly 65 raw identities, 65 normalized assertions and 65 verified fresh receipts | Current |
| NWS live context | Complete success; 3 requests, 158 accepted, 0 rejected | Exactly 158 identities/assertions/fresh receipts | Stale native forecast issue time, truthfully retained |
| WFIGS current | Complete success; 3 requests, valid empty scope snapshot | Source run/cursor/native service timestamp persisted; zero fire identities/assertions | Current |

WFIGS positive-fire row persistence was not exercised by this empty real snapshot.
It is covered by real PostGIS safety/lifecycle tests; no fire was fabricated for
live evidence. NWS HTTP success does not replace its original native forecast time
or turn its stale native freshness into current. Shared NWS dataset counters remain
clearly identified; independent expanded dataset coverage/health is pending Batch 2.

M1 15/15 fixture cases and both independent legacy oracle files remain byte-identical;
nine pipeline cases, 18,000 comparisons, zero mismatches. M2 isolation, G1 order,
F1 reinstatement, F2 privacy (including expired-worker protection), H1 old-edit
receipt safety, quotas/cancellation/Retry-After/backoff and failure recovery passed.
Migration 0009/backfill/repeat/restart/Compose and actual backup.sh/restore.sh passed.
Nonempty collector lease/checkpoint/reference/provenance state survived restore,
alongside existing owner/H3 indexes/report-group/M2 artifacts; zero M2 promotions.

At 100,000 retained explicit CAP barriers, the actual plan used the primary-key
Index Scan and returned one row; median isolated lookup
0.658 ms across ten samples. This is synthetic
load testing in a disposable database, separate from genuine provider evidence.

Changed implementation/deployment/configuration files and commits are listed by
the final receipt; major changes are sources/ownership.py, http.py, storage.py,
inventory.py, diagnostics.py, models.py, config.py, api.py, retention.py, logging.py,
schema version/migration 0009, Compose/locks/Dockerfile, verification/acceptance
tools and targeted tests. Photographic evaluators, M2 engine, HA and migrations
0001–0008 are unchanged. CORE_LIVE_SOURCES=false, patterns off and retention off
remain default; all promotion/notifications/releases remain disabled.

The user will run installed Unraid verification after review. The handoff includes
read-only operator commands and no secret-bearing outputs. Claude independent
acceptance and installed runtime evidence are pending. Remaining provider adapters,
credentials/permissions/licensed storage terms and source-specific coverage must
be completed in later ingestion batches. The full phase is **NOT COMPLETE**.

Batch 1 code and CI = READY FOR INDEPENDENT REVIEW

Installed Unraid collection/persistence = OPERATOR VERIFICATION PENDING

Complete multi-source ingestion = NOT COMPLETE

Production promotion / notifications / release = NO
