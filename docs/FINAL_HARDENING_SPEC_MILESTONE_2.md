You are performing the FINAL HARDENING PASS for:

PHOTOGRAPHY EVENTS CORE
MILESTONE 2 — OBSERVATION INTELLIGENCE & AGGREGATION

This follows the final independent Claude Code review.

DO NOT begin Milestone 3.

DO NOT add live providers.

DO NOT release or promote M2.

The M2 analytical architecture is accepted.

This pass addresses three newly discovered hardening issues before M2 can be
closed and before Milestone 3 may add live source adapters.

==================================================
CURRENT STATUS
==================================================

Independent verdict:

PASS FOR SHADOW EVALUATION
PROMOTION NOT READY

Verified:

- 241 Core tests on real PostGIS
- 96 portable passed / 145 skipped
- ruff clean
- all F-tests present
- both legacy fixtures byte-identical
- 18,000 evaluator comparisons / 0 mismatches
- S1 fixed
- S1-R1 fixed
- S2 fixed
- S3 dense-core rescue fixed
- migration through 0005 works
- privacy holds
- destination protection holds
- M1 remains authoritative
- M2 shadow cannot block M1

Do not redesign those areas.

==================================================
RECEIPTS
==================================================

Reviewed Core code freeze:

1a2410f

Reviewed Core tip:

9ee41f1

HA:

c76726e

Verify current origin/main before editing.

Record actual starting SHAs.

Main-only workflow.

==================================================
WHY THIS PASS EXISTS
==================================================

Three findings remain:

N-A
M2 identity/enrichment work slows M1 collection about 2.7x even when patterns
are OFF.

N-B
`coherence_rejected` can be incorrectly assigned to an unrelated episode.

N-C
A rehomed explicit-origin mirror does not automatically re-collapse when the
canonical record is later corrected to become compatible.

N-A MUST be fixed before any live source adapter.

N-B and N-C must be fixed before promotion.

==================================================
N-A — HIGH PRIORITY
M2 MUST NOT DEGRADE M1 COLLECTION PERFORMANCE
==================================================

Independent reviewer measured on the same PostGIS instance:

M1 accepted code:

approximately 3.3–4.1 ms per record

default 3-second collection capacity:

approximately 730–900 records

Final M2 code with patterns OFF:

approximately 9.9–10.8 ms per record

default 3-second collection capacity:

approximately 280–300 records

A 500-record collection:

M1 code:
completed in approximately 1.86 seconds

M2 code with patterns OFF:
failed with DatabaseUnavailable

Correctness fails safely, but this is still an unacceptable regression.

==================================================
ROOT CAUSE
==================================================

Current collection path invokes M2-specific work such as:

identity.attach
report-group lookups
membership changes
behavior work
rehoming

for every record during the M1 collection transaction.

This happens even when:

CORE_PATTERNS_MODE=off

That violates the architectural boundary we have spent multiple correction
passes establishing:

M2 must not make M1 slower or less reliable when M2 is disabled.

==================================================
AUTHORITATIVE N-A DESIGN PRINCIPLE
==================================================

Prefer architectural isolation over micro-optimization.

M1 COLLECTION must remain primarily responsible for:

- source run
- raw observation persistence
- normalized assertion persistence
- provider corrections
- M1-required normalized fields
- M1 collection truthfulness

M2-specific enrichment should NOT unnecessarily execute inside the M1
collection critical path.

M2-specific examples include:

- report-group resolution
- explicit mirror grouping
- report-group rehoming
- M2 behavior relationships not required by M1
- pattern identity preparation

Where practical:

M1 collect
        ↓
COMMIT
        ↓
M2 enrichment / identity reconciliation
        ↓
M2 pattern run

M2 enrichment failure must not roll back M1 collection.

==================================================
PATTERNS MODE OFF
==================================================

When:

CORE_PATTERNS_MODE=off

M2-specific identity/group/behavior enrichment should perform NO significant
per-record work during M1 collection unless a specific field is genuinely
required by M1.

The performance target is not exact byte-for-byte timing parity with old M1,
but the OFF mode should be close enough that M2 infrastructure no longer
reduces practical collection capacity by roughly two thirds.

Document unavoidable overhead.

==================================================
PATTERNS MODE SHADOW
==================================================

When:

CORE_PATTERNS_MODE=shadow

M1 collection must still commit independently.

M2 identity/enrichment may run:

- asynchronously/post-collection
- during the M2 preparation stage
- in a dedicated bounded enrichment transaction

Choose the simplest maintainable design.

It must not share M1's collection deadline in a way that causes M1 collection
to fail because report grouping is expensive.

==================================================
DO NOT LOSE M2 PROVENANCE
==================================================

Moving enrichment out of M1 collection must NOT weaken:

- report-group provenance
- provider correction handling
- behavior provenance
- current/superseded memberships
- pattern reproducibility
- pattern input fingerprints

M2 may lag briefly behind newly committed M1 observations.

That is acceptable in shadow mode.

Its pattern-run status/provenance must truthfully identify which observations
and enrichment state were actually used.

==================================================
BATCHING
==================================================

Even after decoupling:

avoid one-query-per-record behavior.

Use batch operations where practical for:

- origin lookups
- report-group creation
- membership association
- behavior persistence
- current membership retrieval

Do not introduce Redis/Celery/another queue.

PostgreSQL + the existing scheduler/runtime is sufficient.

==================================================
N-A TESTS
==================================================

Add tests using the DEFAULT production collection timeout.

Do NOT raise DB timeout to 30 seconds.

P1
500 valid records, patterns OFF.

Expected:
M1 collection succeeds within default deadline on the normal test environment.

P2
500 valid records, patterns SHADOW.

Expected:
M1 collection succeeds independently of M2 enrichment duration.

P3
M2 enrichment raises.

Expected:
M1 collection remains committed and truthful.

P4
M2 enrichment is deliberately slow.

Expected:
M1 collection completes without waiting for the slow M2 work.

P5
patterns OFF.

Verify M2 report-group/behavior work is not unnecessarily executed in the M1
per-record path.

P6
provider correction while M2 enrichment is behind.

Expected:
next M2 reconciliation converges to current non-superseded assertions.

P7
large batch followed immediately by M1 generation.

Expected:
M1 remains functional while M2 catches up.

==================================================
N-A BENCHMARK
==================================================

Benchmark with real PostGIS.

Compare:

accepted M1 code behavior
current pre-fix M2 behavior
corrected M2 OFF
corrected M2 SHADOW

At minimum:

100 records
500 records
1000 records

Measure:

collection wall time
per-record equivalent
query count if practical

Do not create a fake hard performance requirement based on one machine.

The acceptance requirement is:

M2 OFF must no longer cause the severe ~2.7x regression discovered by the
reviewer.

M1 collection must succeed for the 500-record regression case at the default
deadline.

==================================================
N-B — COHERENCE REJECTION MISLABEL
==================================================

Independent reproduction:

Episode A's supporting reports age out normally.

In the SAME generation:

an unrelated bear chain approximately 150 km away is rejected by the coherence
guard.

Actual:

Episode A transition reason becomes:

coherence_rejected

Expected:

Episode A should be:

unsupported
expired
or the existing normal no-support reason

The unrelated rejected candidate must not contaminate its transition reason.

==================================================
CAUSE
==================================================

Current episode preparation appears to apply:

coherence_rejected

to every unsupported episode of a phenomenon whenever ANY cluster candidate for
that phenomenon was coherence-rejected.

That scope is too broad.

==================================================
AUTHORITATIVE N-B FIX
==================================================

A coherence rejection may influence an existing episode's transition reason
only if the rejected candidate is plausibly associated with THAT episode.

Use deterministic lineage/proximity information.

Preferred strongest evidence:

prior episode cluster/report membership overlaps the rejected candidate's
relevant reports

or:

the rejected candidate passes the same spatial/temporal continuation
compatibility test that would have allowed it to continue that episode before
coherence rejection.

Do NOT simply match:

same phenomenon_key

Do NOT create fuzzy biological inference.

==================================================
N-B TESTS
==================================================

B1
Episode A ages out.

Unrelated candidate B 150 km away is coherence-rejected.

Expected:
A is NOT labeled coherence_rejected.

B2
Existing episode A's next candidate is directly derived from its recent support
and fails coherence.

Expected:
A may be labeled coherence_rejected.

B3
Two episodes of the same phenomenon.

Rejected candidate corresponds only to episode B.

Expected:
only B gets coherence-rejected diagnostic.

B4
Dense-core fallback recovers cluster.

Expected:
episode reflects recovered support, not coherence rejection.

==================================================
N-C — REHOMED MIRROR RECONCILIATION
==================================================

Current behavior:

A mirror explicitly claims canonical origin X.

At first:

its timestamp is incompatible.

Correct behavior:
mirror is rehomed/unresolved and counts independently.

Later:

canonical origin X is corrected by its provider.

Its timestamp now matches the mirror.

Current behavior:
the mirror remains independent until the mirror itself is redelivered.

This temporarily double-counts one underlying report.

==================================================
AUTHORITATIVE N-C PRINCIPLE
==================================================

Explicit origin claims are durable identity assertions even when temporarily
invalid.

When either side of a claimed identity relationship changes:

re-evaluate the relationship.

Do NOT require only the mirror side to be redelivered.

==================================================
IDENTITY CLAIM MODEL
==================================================

Preserve enough information to answer:

"This record claims origin namespace X / external ID Y."

Even if the current grouping rejected that claim because:

subject mismatch
time mismatch
other definitive consistency failure

The current group membership may be independent/unresolved.

The claim itself should remain inspectable so reconciliation can retry after
either record changes.

If the existing schema already retains this:

reuse it.

Do not create redundant tables.

==================================================
RECONCILIATION
==================================================

On change to a canonical provider record:

find current records with explicit origin claims targeting it.

Re-run the same definitive consistency validator.

If now valid:

rehome/collapse into the canonical report group.

If still invalid:

remain independent.

If previously valid becomes invalid:

split/rehome as current code already supports.

Historical cluster/report-group provenance remains immutable.

Next generation uses corrected CURRENT identity.

==================================================
NO FUZZY DEDUPLICATION
==================================================

This must remain true.

N-C does NOT authorize matching based on:

near coordinates
same species
similar timestamp

It only reevaluates an EXPLICIT origin relationship already supplied by a
trusted adapter.

==================================================
N-C TESTS
==================================================

C1
Mirror claim initially invalid due to time.

Canonical later corrected into valid tolerance.

Expected:
mirror automatically collapses on reconciliation without mirror redelivery.

C2
Canonical changes but remains incompatible.

Expected:
mirror remains independent.

C3
Previously valid canonical changes to incompatible.

Expected:
mirror rehomed/split.

C4
Canonical subject changes to match previously rejected explicit mirror claim.

Expected:
relationship reevaluates deterministically.

C5
No explicit origin claim.

Canonical update must NEVER cause fuzzy collapse.

==================================================
M2 ENRICHMENT CURRENTNESS
==================================================

If N-A introduces asynchronous/post-collection enrichment:

make currentness explicit.

Potential states:

pending
current
failed
outdated

or integrate with existing pattern run semantics.

A pattern run must not silently use half-reconciled identity state.

Choose one simple invariant.

Preferred:

before clustering a pattern run reconciles/ensures M2 enrichment for the exact
current observation set it intends to use.

Then computes a deterministic pattern input fingerprint.

If reconciliation cannot complete:

pattern run fails/degrades in SHADOW only.

M1 remains unaffected.

==================================================
TRANSACTION BOUNDARIES
==================================================

Document final boundaries clearly.

Desired conceptual flow:

SOURCE FETCH

M1 COLLECTION TRANSACTION
- source run
- raw observations
- normalized observations
COMMIT

M1 can proceed normally

M2 ENRICHMENT
- explicit origin identity
- report grouping
- behaviors
- corrections/reconciliation

M2 PATTERN COMPUTE

M2 SHORT PUBLISH

Do not hold M1 publication locks during enrichment or clustering.

==================================================
M1 PARITY
==================================================

Must remain unchanged.

Re-run:

both legacy fixtures
pipeline oracle
18,000 evaluator fuzz

Expected:

byte-identical
0 mismatches

M1 collection semantics must remain correct.

==================================================
M2 REGRESSION
==================================================

All existing:

241 Core tests

must continue passing unless additional tests raise the count.

All:

A-tests
F-tests

must remain passing.

Do not change S3 dense-core rescue semantics.

==================================================
PRIVACY
==================================================

Re-run privacy tests after identity/enrichment refactor.

Moving report grouping outside ingestion must not expose:

exact geometry
analysis geometry
cluster geometry
sensitive radius
private site information

No raw observation data is added to HA.

==================================================
MIGRATION
==================================================

Current migration head:

0005

Do NOT edit committed migrations 0001–0005.

If N-C durable origin-claim reconciliation requires a schema change:

create:

0006

If no schema change is required:

do not create a migration merely to increment the number.

Run full chain:

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
0006 if used

Also test fresh DB → head.

==================================================
BACKUP / RESTORE
==================================================

The independent reviewer did NOT reproduce 0005 backup/restore.

This final hardening pass must run the actual operator scripts if the
environment allows.

Required:

pg_dump -Fc

clean PostGIS target

restore

migration head

ownership

M1 API

M2 shadow/debug reads

report-group identity

episode state

If the environment genuinely cannot execute it:

CI must perform it and the review packet must provide the run.

==================================================
COMPOSE
==================================================

Reviewer could not build the Core image because its environment required a
proxy CA.

That is not a product defect.

Use CI or your implementation environment to verify:

Compose build

DB start

Core start

migration head

health/live

health/ready

M1 request

M2 shadow request

restart behavior

==================================================
CI
==================================================

Run full CI.

No completion declaration while CI is red.

==================================================
REVIEW PACKET
==================================================

Update:

IMPLEMENTATION_REVIEW_MILESTONE_2.md

Add:

# FINAL HARDENING — N-A / N-B / N-C

For each:

review finding

root cause

chosen architecture

files changed

tests

actual results

remaining limitation

==================================================
PERFORMANCE RECEIPT
==================================================

Include a table comparing:

M1 baseline if reproducible

pre-fix M2

post-fix M2 OFF

post-fix M2 SHADOW

for:

100
500
1000

records where practical.

Explicitly state:

default DB timeout

whether collection succeeded

Do not hide failed measurements.

==================================================
SHADOW VS PROMOTION STATUS
==================================================

At completion report separately:

SHADOW SAFE:

YES/NO

LIVE ADAPTER READY:

YES/NO

PROMOTION READY:

YES/NO

Do not collapse these into one "ready" statement.

==================================================
PROMOTION GATES OUTSIDE THIS PASS
==================================================

Even after N-A/N-B/N-C are fixed, production promotion still requires the
already-documented policy/product gates, including:

ecological threshold validation

live provider identity contracts

public destination validation

HA presentation semantics

volume/retention validation

Those are NOT reasons to add new source integrations in this pass.

==================================================
NO M3
==================================================

Still forbidden:

BirdCast
NEXRAD
USGS
CDEC
NWPS
CalHABMAP
CoastWatch
GOES
Sentinel
HPWREN
MBARI

No new live adapters.

No map.

No vision.

No Redis/Celery/Kafka.

==================================================
FINAL ACCEPTANCE FOR M2 ENGINEERING
==================================================

The engineering portion of M2 can be closed when:

N-A fixed

500-record default-deadline regression succeeds

M2 OFF no longer imposes severe ingestion overhead

N-B fixed

N-C fixed

all existing tests pass

new hardening tests pass

M1 parity exact

privacy intact

migration chain passes

backup/restore passes via local/CI

Compose acceptance passes via local/CI

CI green

final independent Claude review returns PASS

==================================================
FINAL RESPONSE
==================================================

Return:

1. concise hardening summary

2. starting/final Core SHA

3. starting/final HA SHA

4. schema/migration change if any

5. N-A implementation

6. N-A benchmark table

7. N-B implementation

8. N-C implementation

9. new test results

10. total Core test count

11. A/F-test results

12. M1 parity results

13. privacy results

14. migration-chain results

15. backup/restore results

16. Compose acceptance

17. CI links/status

18. review packet location

19. remaining limitations

20. explicitly:
    SHADOW SAFE = YES/NO
    LIVE ADAPTER READY = YES/NO
    PROMOTION READY = YES/NO

End EXACTLY with:

READY FOR FINAL MILESTONE 2 ACCEPTANCE REVIEW