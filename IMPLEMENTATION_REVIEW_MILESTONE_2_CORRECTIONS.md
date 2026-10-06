# Milestone 2 required correction review — S1

## Verdict and scope

S1 is corrected: M1 generation/publication commits and returns independently of
M2 shadow computation. M2 no longer extends the M1 transaction, owns its input
fingerprint or records an M1 GenerationFailed on shadow failure.

The user's reconciled correction request supplied S1 and its authoritative
post-commit/compute/short-publication design. No other specific correction issue
was supplied. This pass does not infer an M3 scope or redesign the independently
reviewed identity/behavior/DBSCAN/uncertainty/coherence/count/episode/privacy/
destination algorithms. M2 remains default-off, off/shadow only.

The independent PASS WITH REQUIRED FIXES and reviewed baseline are user-provided
audit receipts. The tests and CI below are this pass's executed evidence; they
are not a claim of independent reviewer approval of the correction.

## Repository receipts

| Repository | Actual clean starting origin/main | Validated correction code SHA |
|---|---|---|
| Core | 8a7f1834ab5e4e5b9c8bb546466588c495294ad8 | 49d95d43f31626f3c6a60e0a272ab6d1a6081678 |
| HA | c76726ece1e485ece03810087927da344289fba7 | unchanged |

Both were fetched and verified clean on main before edits. Main-only normal
commits/pushes; no force push, PR, tag or release. The final documentation
commit SHA and exact-SHA CI are recorded in an external submission receipt,
avoiding a self-referential repository hash. HA is untouched; its existing
[exact-SHA green CI](https://github.com/Tmatz27/Home-assistant-photography-events/actions/runs/37334287547)
remains its validation receipt.

## Actual corrected boundary

1. M1 reads only its existing inputs and calculates its existing fingerprint.
   Pattern input loading, policy hash and engine hash are absent from this path.
2. The existing advisory lock and atomic M1 publication commit complete under
   the existing production pool/deadline.
3. Only a newly published successful M1 assessment schedules a background
   shadow task. Generation returns its M1 result immediately; it never waits
   for shadow completion. Failed/superseded M1 attempts start no shadow work.
4. A separate shadow pool (one connection, no overflow) creates and commits a
   running pattern ledger row keyed by its base assessment. A unique claim
   prevents two workers from publishing the same base.
5. Another shadow transaction captures assertions and source hashes in one
   REPEATABLE READ snapshot. A collector correction between input queries
   cannot mix old assertions with a new source hash.
6. Ordered PostGIS computation runs outside the M1 advisory/pointer lock.
7. Separate shadow staging writes approved destination associations, bulk
   immutable cluster/member/behavior/disposition artifacts and expected counts.
   It still holds no M1 publication lock and assigns no episodes.
8. A short shadow transaction locks assessment_current, verifies it equals
   base_assessment_id, and only then assigns episodes, links clusters, writes
   snapshots/material revisions and marks the run published. Pointer mismatch
   marks the run superseded without any episode/registry/revision mutation.

M2 never changes assessment_current or the M1 run status/fingerprint. An older
run can retain isolated staged artifacts but cannot publish them as current.
The retained episode algorithm is invoked inside only the validated short
shadow publication, rather than during heavy analytical work.

## Deadlines, failure handling and shutdown

CORE_PATTERN_TIMEOUT defaults to 30 seconds **per shadow phase**. Its pool,
connection/statement settings and guard are separate from CORE_DATABASE_TIMEOUT.
The final pointer/episode publication has a separate at-most-one-second guard,
including lock acquisition. Bulk computation and membership writes happen
before this lock. This short lock is an intentional serialization boundary,
not a strict zero-contention latency guarantee on the shared DB server.

Shadow exceptions/timeouts roll back only their own transaction and mark their
own ledger failed with a fixed safe error code. They do not call M1 record_failure,
change production Database.failed, raise M1 GenerationFailed, or degrade newer
production safety decisions. No arbitrary exception strings enter logs/DTOs.
Failure recording is bounded and best effort if the DB itself is unavailable.

Shutdown cancels/drains owned background tasks. The shadow transaction explicitly
invalidates a driver terminated during cancellation, so failure recording does
not reuse a dead pool connection. Both pools are disposed. Intentional
cancellation records shadow_cancelled where DB recording remains possible.

The explicit developer/test await db.wait_for_patterns() drain exists solely
for scripts requiring completed analysis. Production generation never calls it.
A process crash can leave a running ledger; there is no new durable scheduler,
automatic retry/recovery service or broker. Current debug then remains unassessed.

## Migration and API boundary

[Migration 0004 inventory](docs/SCHEMA_0004.md) adds lifecycle status/start/completion,
independent input fingerprint and safe error code plus checks/index. It adds no
tables and leaves migrations 0001/0002/0003 untouched. Existing 0003 run hashes
and timestamps are preserved by a real seeded upgrade test.

Authenticated debug exposes current-base artifacts only when its pattern run is
published. Pending/failed/missing/superseded coverage is unassessed with empty
items/clusters/previews. A failed shadow result does not affect normal Core
opportunity responses. Privacy whitelists, approved destinations and held
preview eligibility remain intact; no HA consumer, promotion mode or public
travel authority was added.

## Executed regression matrix

[Code CI 37414083448](https://github.com/Tmatz27/photography-events-core/actions/runs/37414083448):
**SUCCESS**, exact SHA 49d95d43f31626f3c6a60e0a272ab6d1a6081678.
[Machine evidence](docs/validation/milestone-2-corrections/README.md).

| Gate | Actual result |
|---|---|
| Full PostgreSQL 18.6 / PostGIS 3.6.4 suite | 218 passed, no failures/skips, 19.49 s |
| Original Core baseline | All original 210 tests retained and pass; failure-boundary expectation corrected |
| A1–A38 | All 38 individually collected and passed |
| Added S1 real-DB tests | 8 passed |
| Linux portable | 96 passed, 122 DB skipped; 0.85 s |
| Windows portable | 91 passed, 127 skipped (122 DB + five POSIX) |
| Ruff / compile / offline Alembic | Passed |
| Pinned legacy fixtures | Byte-identical, 15 evaluator cases × 24 fields; nine pipeline cases / 14 steps |
| Legacy evaluator fuzz | 18,000 comparisons, zero mismatches |
| Independent Euclidean DBSCAN oracle | 150 seeded random point sets, zero differences |
| Ambiguous-border input order | Retained six-shuffle test passed |
| Migration | Fresh 0004; real 0001→0002→0003→0004; seeded 0003 shadow history preserved; repeat head passed |
| Core and DB restarts | Persistent episode key preserved |
| Actual backup/fresh restore | Operator scripts passed; 281,148-byte custom archive; episode/history preserved |
| Frozen/stopped DB | Eight warm/eight cold bounded calls, zero leaked checkouts, recovery passed |
| Privacy/destination/report-group corrections | All retained adversarial tests passed |

The independent oracle in test_shadow_boundary.py computes Euclidean
neighborhoods/core connected components independently of production code and
compares actual production SQL partitions over 150 sets. Those randomized sets
avoid shared-border ambiguity; the retained dedicated ambiguity test covers
stable SQL ordering separately. Trials are not inflated into pytest counts.

### New test receipts

| Test | Input / failure | Actual asserted outcome |
|---|---|---|
| test_s1_shadow_exception_cannot_fail_m1_or_hold_new_safety | Throw in shadow compute after fresh safety input | M1 published/complete and safety assessed; only shadow failed; no M1 failed run |
| test_s1_blocked_computation_releases_m1_lock_and_response | Pause compute while holding the one-slot shadow pool | M1 returns and a newer generation publishes before release; old shadow superseded |
| test_s1_real_shadow_timeout_does_not_poison_production_pool | Actual pg_sleep(5), shadow guard 0.15 s, M1 deadline 3 s | M1 stays complete; shadow failed; both pools release checkouts; ready succeeds |
| test_s1_stale_staged_artifacts_cannot_mutate_episode_registry | Pause staged old candidate, publish newer M1 | Old run superseded; episode registry/revisions unchanged; no old snapshots/episode links |
| test_s1_m1_fingerprint_independent_of_shadow_policy_engine | Switch off→shadow, change engine hash and policies at same watermark | M1 semantic fingerprint unchanged; replay superseded without input_conflict |
| test_s1_shutdown_cancels_shadow_without_changing_m1 | Cancel paused worker through Database.close | M1 remains published; run failed/shadow_cancelled; task set drained |
| test_s1_preserves_150_randomized_dbscan_point_sets | Actual PostGIS versus independent neighborhood oracle | All 150 partitions match |
| test_s1_input_capture_keeps_assertions_and_source_hash_in_one_snapshot | Collector commits an additional report during paused capture | Old assertions and old source hashes stay consistent; no mixed snapshot |

Initial correction runs 37413639970 and 37413777515 failed on pointer-lock race
and cancellation cleanup tests. These were fixed, not waived: bounded lock
waiting replaced NOWAIT; cancellation invalidates the dead shadow connection.
Run 37413952555 and the measured code-freeze run above then passed all 218.
Failure artifacts are retained in workspace scratch and are not reported as green.

## Measured production/shadow separation

Real CI, 1,000 synthetic density points, three off/shadow pairs with the default
three-second M1 deadline restored after fixture ingestion:

| Measurement | Seconds |
|---|---|
| M1 publication, off | 0.016797, 0.015051, 0.014202 |
| M1 publication, shadow | 0.015403, 0.014062, 0.013868 |
| Explicitly drained shadow completion including M1 | 0.103770, 0.087653, 0.083492 |

Median shadow/off **M1 publication** ratio is 0.934 for this small warm fixture
sample. This does not claim a universal speedup or production SLA. It shows the
caller no longer waits for the separately measured shadow completion. The
event-driven pause and real pg_sleep tests establish failure/lock/pool isolation
without relying on a timing ratio alone.

Input loading 0.017917 s, clustering 0.023658 s. Full EXPLAIN ANALYZE plans are in
m2-performance.json. These query timings exclude ingestion and do not establish
global-volume support. Shared PostgreSQL/OS/event-loop resource contention
still exists; heavy computation no longer holds the M1 publication lock.

## Preserved scope, remaining limits and independent review

Identity, behavior vocabulary/policies, uncertainty admission, coherence,
MAX counts, episode matching/split/merge logic, destination protection and
privacy rules were not redesigned. episodes.py changed only its module
boundary description; its analytical implementation is unchanged. Policy,
identity and clustering source files plus migration 0003 and legacy fixtures
are byte-unchanged against the reviewed tip.

All [original known limitations/deferred scope](IMPLEMENTATION_REVIEW_MILESTONE_2.md#36-known-limitations)
remain. Additional lifecycle limits: per-phase rather than entire-run deadline,
best-effort failure persistence, no crash-resume/retry worker, modest-scale
queued background work, shared DB resource contention and the bounded short
pointer lock. Independent review should challenge pointer races, cancellation,
input snapshots, stale staged artifacts and the fixed error/privacy boundary.

No M3, new source family, release/tag/version bump, production-default M2, HA
cutover, ML, fuzzy dedupe, map, vision, Redis/Celery or broker is added.
Core product version remains 0.1.0-dev; only schema advances to 0004.
