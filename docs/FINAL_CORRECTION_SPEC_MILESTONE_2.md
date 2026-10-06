You are performing the FINAL CORRECTION PASS for:

PHOTOGRAPHY EVENTS CORE
MILESTONE 2 — OBSERVATION INTELLIGENCE & AGGREGATION

This follows an independent read-only Claude Code review of the S1 boundary
correction.

Do NOT begin Milestone 3.

Do NOT add sources.

Do NOT release M2.

Do NOT redesign the M2 architecture.

The analytical core remains accepted.

==================================================
CURRENT REVIEW VERDICT
==================================================

PASS WITH ONE REQUIRED S1 FIX

The reviewer verified that:

- M2 now starts only after M1 commits
- pattern failure no longer fails M1
- M2 no longer affects the M1 fingerprint
- S2 is fixed
- M1 parity is unchanged
- M2 volume no longer materially increases M1 compute time
- M2 identity/clustering/episode/privacy architecture remains sound

However:

S1-R1 remains open.

S3 also remains open from the previous M2 review and is still required before
pattern promotion.

==================================================
VERIFIED RECEIPTS
==================================================

Core reviewed code freeze:

49d95d4

Reviewed tip:

9194e97

HA:

c76726e

The post-freeze migration-file changes were verified as whitespace-only.

Before editing:

git checkout main
git pull --ff-only

Record actual starting SHAs.

Main only.

==================================================
S1-R1 — HIGH
SERVER-SIDE SHADOW FINISH CAN STILL BLOCK M1
==================================================

Current architecture is mostly correct:

M1 commits first.

M2 compute runs independently.

M2 then enters `finish()` to validate the base assessment and publish episode
state.

The remaining defect is inside this final finish phase.

The reviewer injected:

pg_sleep(6)

inside episode assignment after:

SELECT ... FROM assessment_current FOR UPDATE

had acquired the row lock.

The Python/client bound was 1 second.

However PostgreSQL kept executing the server-side statement after the client
timed out.

A subsequent M1 safety generation then blocked on that row and failed after its
own 3-second deadline.

Observed:

M1 #3:
DatabaseUnavailable after ~3.05 seconds

new High Wind safety state:
not published

shadow run:
correctly marked shadow_failed

The failure is therefore:

client-side timeout != server-side lock release

This must be fixed.

==================================================
AUTHORITATIVE FIX
==================================================

Use BOTH architectural minimization and PostgreSQL server-side limits.

Do not rely only on a Python timeout.

==================================================
1. MINIMIZE THE LOCKED SECTION
==================================================

Review `engine.finish()`.

The `assessment_current` row lock must be held for the shortest practical
period.

Any work that can safely occur BEFORE the lock should occur before it.

In particular, expensive/non-trivial computation should happen before:

SELECT ... FOR UPDATE

The locked transaction should ideally contain only:

1. apply server-side timeout settings
2. lock/read current assessment
3. verify:
   assessment_current == base_assessment_id
4. perform the minimal deterministic episode/publication mutation
5. commit

Do not perform expensive spatial computation while holding the M1 pointer lock.

If episode assignment currently performs meaningful expensive computation after
the lock is taken:

split it into:

PREPARE
compute proposed episode actions without holding M1 pointer

then:

COMMIT
lock pointer
re-check assumptions
apply prepared state atomically

If preparation becomes invalid because M1 advanced:

mark the M2 run superseded.

Do not publish stale state.

==================================================
2. SERVER-SIDE lock_timeout
==================================================

Inside the final shadow publication transaction, BEFORE attempting the pointer
lock, set a transaction-local PostgreSQL:

lock_timeout

equal to or less than the allowed shadow-finish bound.

Target:

~1 second

Use:

SET LOCAL

or the SQLAlchemy/PostgreSQL equivalent.

This must apply at the PostgreSQL server, not only in Python.

If the lock cannot be obtained within the limit:

the pattern run fails/supersedes safely

M1 is unaffected.

==================================================
3. SERVER-SIDE statement_timeout
==================================================

Also set transaction-local:

statement_timeout

for the M2 finish transaction.

Target:

the same bounded finish budget or a deliberately documented small value.

Do NOT leave the shadow pool's global:

60-second statement_timeout

as the effective bound for the locked final publication phase.

The final M2 publication transaction must not retain a lock for tens of seconds
after the client has already abandoned it.

==================================================
4. OPTIONAL idle_in_transaction_session_timeout
==================================================

You may add a conservative shadow-pool:

idle_in_transaction_session_timeout

as defense-in-depth.

Do NOT treat it as the primary S1-R1 fix.

It does not solve an actively executing slow SQL statement.

==================================================
5. CLIENT TIMEOUT REMAINS
==================================================

Keep the Python/client deadline as a second layer.

We want:

client bound
+
server statement bound
+
server lock bound

not:

client timeout only.

==================================================
S1-R1 REQUIRED REGRESSION
==================================================

Create a real-Postgres regression test matching Claude's attack.

Scenario:

1. M1 #1 exists.
2. Publish M1 #2.
3. Its shadow run reaches finish.
4. Inject a server-side slow statement inside the locked finish path.
5. Wait until the shadow finish holds/attempts the pointer lock.
6. Collect newer HIGH WIND safety data.
7. Publish M1 #3 using the DEFAULT production DB deadline.

Expected:

M1 #3 publishes successfully.

It does NOT return:

DatabaseUnavailable

because of the shadow run.

The M2 run becomes:

shadow_failed
superseded
timeout

or another documented safe state.

After cleanup:

0 leaked/check-out connections.

The DB pool remains healthy.

==================================================
ADD LOCK-CONTENTION TEST
==================================================

Also test the inverse:

M1 currently holds its short publication lock.

M2 finish attempts to acquire it.

Expected:

M2 times out safely according to its own lock_timeout.

M1 succeeds.

M2 never gets priority over M1.

==================================================
CANCELLATION NOTE
==================================================

Reviewer found:

engine.run catches CancelledError,
records the failure,
then swallows cancellation.

Correct this while touching the boundary.

Desired behavior:

catch CancelledError separately

perform only bounded/best-effort cleanup/diagnostic recording

then:

raise

Cancellation must propagate to the caller.

Do NOT convert cancellation into an ordinary successful return.

Do NOT catch BaseException generally.

Add a regression test.

==================================================
DOCUMENT SHADOW INPUT TIMING
==================================================

Reviewer confirmed another deliberate behavior:

M2 may begin after M1 commits and then observe pattern inputs collected after
that M1 assessment.

This is acceptable because:

pattern_generation_sources

records the exact source runs actually consumed.

Do NOT attempt to force M2 to pretend those inputs existed at M1 publication.

Document clearly:

M1 base assessment identity
!=
claim that every M2 input existed at base-assessment time

The pattern run's own provenance determines its actual data freshness.

==================================================
M1 STALE-STATISTICS NOTE
==================================================

Reviewer observed one unrelated M1 slowdown after bulk table loading/truncation.

With planner statistics held constant:

M1 generation was consistently approximately:

0.13–0.20 seconds

with shadow both off and on.

This is NOT currently attributed to M2.

Do not broaden this correction pass into a planner/autovacuum redesign.

Record it as an operational/performance backlog item.

If a simple ANALYZE step is already appropriate in benchmark/test setup, that
is fine.

Do not mask actual production behavior merely to make timing tests pass.

==================================================
S3 — STILL OPEN
CHAIN-BRIDGE FALSE NEGATIVE
==================================================

The previous independent M2 review found:

6 tightly grouped bear reports

produced:

one qualified episode

Then adding:

5 sparse reports stepping outward by approximately 2.7 km

caused DBSCAN to link all 11.

The coherence check rejected the full 11-point cluster.

Result:

0 clusters

previous valid episode:
unsupported

This avoids a FALSE POSITIVE but creates a meaningful FALSE NEGATIVE.

For a regret-prevention product, this must be corrected before promotion.

==================================================
S3 PART A
COHERENCE-REJECTED STATE
==================================================

Do not represent this as merely:

unsupported

Persist/debug a specific analytical outcome:

coherence_rejected

or equivalent.

Debug provenance should show:

phenomenon key

candidate observation count

independent report count

primary eps

candidate radius/diameter

configured maximum diameter

fallback attempted

fallback policy

fallback result

No protected geometry in public/debug serialization.

==================================================
S3 PART B
ONE-PASS DENSE-CORE RESCUE
==================================================

Implement the previously specified conservative rescue.

Do NOT build recursive clustering.

Do NOT add ML.

Add optional policy field:

coherence_fallback_eps_meters

or equivalent.

Algorithm:

1. Apply normal phenomenon temporal filtering.
2. Apply normal DBSCAN with primary eps.
3. Candidate cluster fails coherence maximum.
4. Record primary coherence rejection.
5. If no fallback configured:
   reject candidate.
6. If fallback configured:
   run DBSCAN ONE ADDITIONAL TIME
   using only the rejected candidate's members
   and the stricter fallback eps.
7. Apply all normal constraints to fallback clusters:
   - minimum independent reports
   - precision requirements
   - maximum diameter
   - behavior gates
   - count gates
   - privacy rules
8. Accept coherent dense-core subclusters.
9. Remaining points are noise/not promoted.
10. Stop.

No third pass.

No recursion.

No automatic eps/2 unless the phenomenon policy explicitly defines that value.

==================================================
S3 TEST
==================================================

Reproduce Claude's bear chain case.

Expected:

tight six-report core survives.

Sparse stepping reports do not cause the core to disappear.

No 11-report mega-cluster is accepted.

Debug evidence records that:

primary candidate failed coherence

fallback recovered the dense core

==================================================
S3 NEGATIVE TEST
==================================================

Construct a true chain with no meaningful dense core.

Expected:

primary cluster rejected.

fallback produces no qualifying subcluster.

No episode created/promoted.

Debug:

coherence_rejected

==================================================
COUNT SEMANTICS CHECK
==================================================

From the previous independent review, ensure the NULL count issue is fixed if
it has not already been fixed.

NULL animal count means:

unknown

not:

0

A count-required phenomenon must not pass merely because:

(max_single_report_count or 0) >= 0

If count_requirement = 0 has no useful semantic meaning:

validate and reject that policy configuration.

Add explicit tests.

==================================================
MIRROR IDENTITY CHECK
==================================================

From the previous independent review, confirm whether the origin-identity
consistency checks were implemented.

A trusted mirror claiming an existing explicit origin must not silently attach
if:

subject/taxon is incompatible

or:

authoritative observation time is absurdly incompatible

This is NOT fuzzy deduplication.

It is validation of a claimed definitive identity relationship.

If this remains unimplemented:

implement the adapter identity consistency hook now.

On mismatch:

do not collapse

record sanitized:
origin_identity_mismatch

treat as unresolved/independent

Do not use geographic proximity alone as proof.

==================================================
BOUNDED INPUT QUERY
==================================================

Confirm the pattern input loader no longer loads unlimited historical
assertions only to reject them in Python.

The SQL query should apply a broad maximum M2 temporal working window derived
from enabled policies.

Then phenomenon-specific filtering occurs in Python/engine logic.

If still unbounded:

fix now.

Test old history is not loaded.

==================================================
BUGLING BACKFILL
==================================================

Confirm whether the legacy:

bugling -> rut

0004 correction was implemented.

If it was not:

fix through a NEW forward migration.

Do NOT edit historical migrations already shipped in repository history.

If 0004 already exists for the shadow boundary and the data correction is not
there, create the next migration rather than rewriting 0004 after it has been
reviewed.

Migration numbering must remain append-only.

==================================================
MIGRATIONS
==================================================

DO NOT rewrite:

0001
0002
0003
0004

after they have been committed/reviewed.

If this pass requires schema/data migration beyond the existing 0004:

create:

0005

with a descriptive name.

Run:

0001
→
0002
→
0003
→
0004
→
0005 if applicable

and:

fresh DB
→ latest head

==================================================
M2 SHADOW ACCEPTANCE
==================================================

After S1-R1 is fixed:

M2 SHADOW MODE may be considered safe for evaluation.

Shadow mode means:

M1 production remains authoritative.

M2 may compute.

M2 may fail.

M2 may be stale.

M2 may be superseded.

None of those states affect M1 availability or correctness.

==================================================
M2 PROMOTION ACCEPTANCE
==================================================

Do NOT call M2 ready for promotion until:

S1-R1 fixed

S3 dense-core recovery fixed

count NULL semantics correct

origin-identity validation correct

input query bounded

all A-tests pass

all correction tests pass

final independent review passes

biological thresholds intended for live use have been separately reviewed

==================================================
NEW TESTS
==================================================

Add at minimum:

F1
slow server-side statement inside M2 finish cannot block M1 publication.

F2
M2 lock acquisition timeout leaves M1 unaffected.

F3
M2 server statement timeout aborts transaction and releases lock.

F4
no shadow pool connection leak after server-side timeout.

F5
CancelledError propagates after bounded cleanup.

F6
tight bear core + sparse bridge recovers dense core.

F7
pure sparse chain produces no false cluster.

F8
debug distinguishes coherence_rejected from unsupported.

F9
NULL count cannot satisfy count-required policy.

F10
origin identity with incompatible subject does not collapse.

F11
origin identity with incompatible authoritative time does not collapse.

F12
valid origin identity still collapses correctly.

F13
SQL input loader excludes observations older than global active M2 window.

F14
M1 publication latency remains bounded while M2 finish is stalled.

Use real PostGIS for all DB/locking behavior tests.

==================================================
RE-RUN ALL EXISTING TESTS
==================================================

All existing:

218 Core tests

must remain green.

All M2 A-tests must remain green.

M1 parity must remain:

byte-identical fixtures

18,000 / 0 evaluator mismatch

Do not modify M1 policy to satisfy M2 tests.

==================================================
PERFORMANCE
==================================================

Measure separately:

M1 generation/publication

M2 compute

M2 finish/publish

under representative input counts.

The critical assertion is:

M2 finish cannot make M1 exceed its own deadline.

Do not claim M2 total runtime must be under M1's deadline.

That architectural coupling is intentionally gone.

==================================================
BACKUP / RESTORE
==================================================

If migration head changes:

rerun:

pg_dump -Fc

restore into clean PostGIS DB

verify:

ownership
migration head
M1 API
M2 debug state
episode state

==================================================
CI
==================================================

Run the full CI suite.

Do not declare complete if CI is red.

==================================================
REVIEW PACKET
==================================================

Update:

IMPLEMENTATION_REVIEW_MILESTONE_2.md

Add a section:

FINAL INDEPENDENT CORRECTION PASS

Record:

S1-R1

CancelledError note

shadow input timing note

S3

count semantics

identity validation

input-loader bound

migration changes

For every finding:

reviewer reproduction

fix

test

result

==================================================
DO NOT RELEASE
==================================================

No:

tag
release
production notification
M2 promotion
new sources
map
vision
Milestone 3 work

==================================================
FINAL RESPONSE
==================================================

Return:

1. concise summary

2. starting/final Core SHA

3. starting/final HA SHA

4. migration head and changes

5. S1-R1 result

6. cancellation result

7. S3 dense-core result

8. count-semantics result

9. mirror-identity result

10. bounded-input-query result

11. F1-F14 results

12. total Core test count

13. A-test status

14. M1 parity status

15. M1/M2 timing measurements

16. migration-chain result

17. backup/restore result

18. CI results/links

19. review packet path

20. every remaining known limitation

21. explicit statement:
    shadow-safe yes/no
    promotion-ready yes/no

End EXACTLY with:

READY FOR FINAL INDEPENDENT MILESTONE 2 REVIEW