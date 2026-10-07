You are performing a NARROW PRE-MILESTONE-3 HARDENING PASS for:

PHOTOGRAPHY EVENTS CORE

The only required engineering objective is:

H3 — bound M2 identity reconciliation so accumulated historical normalized
assertions cannot permanently break shadow processing.

Do NOT begin Milestone 3.

Do NOT add live providers.

Do NOT redesign Milestone 2.

Do NOT change ecological policies.

Do NOT release or promote M2.

==================================================
CURRENT ACCEPTED STATE
==================================================

Milestone 2 engineering closure has independently PASSED.

Accepted state:

Core tip reviewed:
c1db87e

HA:
c76726e

Independent review reproduced:

- 261 Core tests on PostgreSQL 18 / PostGIS 3.6
- 96 portable passed / 165 skipped
- ruff clean
- M1 fixtures byte-identical
- 18,000 evaluator comparisons / 0 mismatches

Previously discovered issues are fixed:

N-A:
M1 collection performance restored

N-B:
coherence_rejected no longer contaminates unrelated episodes

N-C:
rehomed mirrors automatically re-collapse after canonical correction

M2 is:

SHADOW SAFE = YES

LIVE ADAPTER READY = NO

PROMOTION READY = NO

H3 is the remaining engineering gate before live adapters.

==================================================
H3 REPRODUCTION
==================================================

Current identity reconciliation scans:

EVERY current trusted normalized assertion

on every shadow run.

Old observations stay current indefinitely unless superseded.

There is no normalized-observation retention yet.

Independent reviewer reproduced:

2,000 old current assertions:
~0.46 s
published

5,000:
~0.82 s
published

10,000:
~0.97 s
shadow_failed

The relevant shadow transaction budget is approximately:

900 ms server-side

Once enough historical records accumulate, every future shadow run fails.

M1 remains safe, but M2 never recovers without intervention.

This is unacceptable before live observation adapters.

==================================================
AUTHORITATIVE H3 STRATEGY
==================================================

Implement:

BOUNDED IDENTITY RECONCILIATION

Do NOT implement a full incremental/change-watermark engine unless inspection
proves bounded reconciliation cannot satisfy the requirements.

The goal is simple:

identity.reconcile must operate only on rows that can matter to the current
pattern run.

==================================================
ACTIVE WORKING WINDOW
==================================================

Determine the maximum currently enabled M2 observation window across the
phenomenon policies involved in the run.

Conceptually:

max_active_window =
max(policy.temporal_window for enabled pattern policies)

Also include any explicitly defined:

future observation tolerance

if required by current semantics.

Build a database cutoff such as:

evaluation_time - max_active_window

Do NOT scan all historical current assertions.

==================================================
PRIMARY RECONCILIATION SET
==================================================

Load CURRENT, non-superseded normalized observations that satisfy the bounded
working window.

Apply other existing eligibility filters where safe and queryable.

At minimum avoid pulling:

60-day-old
90-day-old
year-old

current assertions when all active M2 policies only use a much shorter window.

==================================================
EXPLICIT ORIGIN CLAIM EXCEPTION
==================================================

This is CRITICAL.

The bounded time window must NOT break explicit mirror identity.

If a relevant observation carries an explicit trusted origin claim:

origin_namespace
origin_external_id

the reconciliation set must also include the canonical target required to
resolve that claim, EVEN IF that canonical target lies outside the ordinary
working time window.

Likewise, where a relevant canonical record has current explicit claimants that
must be reconciled after a provider correction, load those claimants as needed.

Therefore the working set is conceptually:

ACTIVE WINDOW OBSERVATIONS

PLUS

IDENTITY DEPENDENCIES OF THOSE OBSERVATIONS

not:

every historical assertion

and not:

active-window rows only

==================================================
DO NOT CREATE FALSE IDENTITY
==================================================

All current M2 identity rules remain unchanged.

Still:

same provider + stable ID
= same provider record

trusted explicit origin relationship
= eligible for definitive mirror grouping

fuzzy:
same species
near coordinates
similar timestamp

does NOT auto-collapse.

Do not loosen identity merely to simplify the bounded query.

==================================================
CLAIM DEPENDENCY QUERY
==================================================

Implement the reconciliation working-set query efficiently.

Avoid:

one query per observation

Prefer:

bounded bulk query
+
bulk canonical-target lookup
+
bulk claimant lookup where needed

Use existing indexes or add narrowly justified indexes if query plans show a
need.

Do not add speculative indexing.

==================================================
RECONCILIATION SEMANTICS
==================================================

For every identity relationship inside the bounded dependency graph:

preserve existing behavior:

valid explicit mirror
→ collapse

invalid explicit mirror
→ unresolved/independent

canonical correction makes previously invalid claim valid
→ re-collapse

canonical correction makes previously valid claim invalid
→ rehome/split

Historical cluster/report provenance remains immutable.

Current report membership changes only affect future pattern generations.

==================================================
OLD UNRELATED ASSERTIONS
==================================================

Historical assertions outside:

the M2 active working window

and:

any explicit origin dependency

must NOT be scanned or reconciled during a normal current pattern run.

They remain stored.

This task is NOT retention.

Do not delete them.

Do not supersede them merely because they are old.

==================================================
PATTERN FINGERPRINT
==================================================

The bounded reconciliation optimization must not make pattern fingerprints
non-deterministic.

The pattern run should fingerprint the actual logical current inputs it uses.

Historical irrelevant rows outside the working/dependency set should not affect:

pattern_input_fingerprint

cluster membership

episode decisions

==================================================
H3 PERFORMANCE ACCEPTANCE
==================================================

Reproduce the original cliff using real PostGIS.

Create:

10,000 old current assertions

at least 60 days old

outside every enabled pattern policy window

Then add a small fresh relevant pattern input.

Run at production/default settings.

Expected:

shadow run publishes successfully.

It must NOT become:

shadow_failed

because the 10,000 irrelevant rows exist.

==================================================
LARGER SCALE TEST
==================================================

Also test:

25,000 old irrelevant current assertions

if practical in CI/test runtime.

This is not a new production performance promise.

It is simply evidence that query cost is based on the active working set rather
than total retained history.

==================================================
IDENTITY DEPENDENCY TESTS
==================================================

Add at minimum:

H3-1
10,000 old unrelated assertions + 4 fresh relevant reports.

Expected:
pattern publishes successfully.

H3-2
Old canonical record outside active window.

Fresh mirror inside active window explicitly references it.

Expected:
canonical target is still loaded and mirror identity resolves correctly.

H3-3
Fresh canonical record inside window.

Older explicit claimant outside normal window still requires reconciliation
because canonical was corrected.

Expected:
claim relationship updates correctly where current identity semantics require
it.

H3-4
10,000 old rows with no relationship to active observations.

Expected:
they do not appear in the reconciliation working set.

H3-5
Shuffled DB insertion/input order.

Expected:
same grouping/fingerprint/result.

H3-6
Provider correction moves a currently relevant assertion outside the active
window.

Expected:
next pattern generation no longer uses it.

Historical provenance remains unchanged.

H3-7
Provider correction moves an older assertion back into relevance.

Expected:
it becomes eligible and reconciliation works normally.

==================================================
QUERY PLAN / INDEX REVIEW
==================================================

Use EXPLAIN or EXPLAIN ANALYZE on representative reconciliation queries.

Document:

query plan

indexes used

rows scanned

rows returned

for:

small DB

10,000 historical rows

large historical + tiny active set

The desired property:

rows processed should scale primarily with the active/dependency working set,
not total historical current assertion count.

==================================================
IDENTITY MISMATCH LOG SPAM
==================================================

Independent review also noted:

origin_identity_mismatch

is currently emitted every pattern run for the same persistent unresolved
mismatch.

This is non-blocking but should be corrected in this hardening pass if cleanly
possible.

Prefer event emission when identity status CHANGES.

Examples:

valid → mismatch
mismatch → valid
new mismatch

Do not repeatedly emit identical mismatch events every generation.

Preserve current state/provenance even if no log event is emitted.

Add a test.

==================================================
DO NOT ADD RETENTION YET
==================================================

H3 does NOT require deleting historical normalized observations.

Retention policy remains a separate pre-production/operations decision.

Do not solve query efficiency by deleting evidence required for historical
provenance.

==================================================
DO NOT MOVE BACK INTO M1
==================================================

M2 reconciliation remains outside the M1 collection/publication critical path.

Do not regress N-A.

Patterns OFF must continue to avoid the M2 performance tax.

M1 collection remains authoritative and independent.

==================================================
M1 REGRESSION
==================================================

Re-run all existing M1 parity validation:

both legacy fixtures

pipeline oracle

18,000 evaluator comparisons

Expected:

byte-identical
0 mismatches

Do not change M1 policy.

==================================================
M2 REGRESSION
==================================================

All existing:

261 Core tests

must remain passing unless test count increases.

All prior:

A tests
F tests
P/B/C tests

must remain passing.

Specifically re-run:

N-A performance regression
N-B episode-label test
N-C canonical correction/re-collapse
S1/S1-R1 isolation
S3 dense-core rescue
privacy tests

==================================================
MIGRATION
==================================================

Current schema head:

0005

Do NOT modify migrations 0001–0005.

If H3 requires a new DB index/schema field:

create 0006.

If it does not:

do not create a migration.

Run:

0001
→
0002
→
0003
→
0004
→
0005
→
0006 if applicable

and:

fresh DB → head

==================================================
BACKUP / RESTORE
==================================================

If schema changes:

re-run backup and restore.

If no schema changes:

existing accepted schema backup behavior need not be redesigned, but CI should
remain green.

==================================================
CI
==================================================

Run full CI.

Do not report completion while CI is red.

==================================================
REVIEW PACKET
==================================================

Update:

IMPLEMENTATION_REVIEW_MILESTONE_2.md

Add section:

H3 PRE-LIVE-ADAPTER HARDENING

Document:

- original finding
- old unbounded query behavior
- new bounded working-set definition
- identity dependency handling
- canonical-target exception
- indexes/query plans
- performance results
- mismatch logging behavior
- tests
- known limits

==================================================
NO MILESTONE 3
==================================================

Do NOT add:

BirdCast
eBird live adapter changes
iNaturalist live adapter changes
GBIF
USGS
CDEC
NWPS
CalHABMAP
CoastWatch
GOES
Sentinel
HPWREN
MBARI

No live adapters.

No map.

No vision.

No production promotion.

==================================================
FINAL STATUS TERMINOLOGY
==================================================

After this pass report:

M2 ENGINEERING CLOSED = YES/NO

SHADOW SAFE = YES/NO

LIVE-ADAPTER ENGINEERING READY = YES/NO

PROMOTION READY = NO

Promotion remains blocked by:

ecological threshold validation

live source contracts

public destination validation

HA product semantics

volume/retention validation

Those are later product/source gates, not H3.

==================================================
FINAL RESPONSE
==================================================

Return:

1. concise H3 fix summary

2. starting/final Core SHA

3. HA SHA / confirmation unchanged

4. schema migration if any

5. bounded reconciliation design

6. identity dependency behavior

7. H3-1 through H3-7 results

8. 10,000-old-row timing

9. 25,000-old-row timing if run

10. EXPLAIN/query-plan summary

11. mismatch-log dedup result

12. total Core test count

13. M1 parity results

14. prior M2 regression results

15. migration results

16. CI status/links

17. review packet path

18. remaining known limitations

19. state explicitly:

M2 ENGINEERING CLOSED = YES/NO
SHADOW SAFE = YES/NO
LIVE-ADAPTER ENGINEERING READY = YES/NO
PROMOTION READY = NO

End EXACTLY with:

READY FOR H3 INDEPENDENT VERIFICATION