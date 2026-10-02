You are the PRIMARY IMPLEMENTER performing the REQUIRED CORRECTION PASS for
Photography Events Core Milestone 1.

This prompt follows:

1. your original Milestone-1 implementation
2. an independent read-only Claude Code audit
3. ChatGPT reconciliation of the audit findings

Do NOT broaden the project.

Do NOT begin Milestone 2.

Do NOT add new data sources.

Do NOT release v0.17.

The purpose of this pass is to make Milestone 1 actually satisfy its
correctness, persistence, provenance, outage and parity guarantees.

==================================================
AUTHORITATIVE REPOSITORIES
==================================================

Core:

Tmatz27/photography-events-core

Home Assistant:

Tmatz27/Home-assistant-photography-events

Reviewer-observed SHAs before this correction pass:

Core:
aebc9a1

HA:
7a9d4c6

Verify these yourself before editing.

If remote main has moved, STOP and report the discrepancy before making
unrelated assumptions.

Use MAIN ONLY.

Do not work on:

claude/kind-volta-6jwwdd

or another reviewer branch.

Before editing each repository:

git checkout main
git pull --ff-only

Record the exact starting SHA.

==================================================
INDEPENDENT REVIEW RESULT
==================================================

The independent reviewer returned:

PASS WITH REQUIRED FIXES

The architecture does NOT require redesign.

The evaluator port itself performed extremely well.

Independently reproduced:

- 71/71 Core tests against real PostgreSQL 18.6 / PostGIS 3.6.4
- 53 portable Core tests passed, 18 skipped without DB
- Alembic repeat upgrade and downgrade/upgrade
- 15/15 legacy Tule Elk parity cases, byte-identical recapture
- 18,000 randomized evaluator comparisons
- 0 evaluator mismatches
- restore ownership verification
- DB stop/recovery behavior
- 13 HA Core-client tests
- 575 HA portable tests
- 127/127 card tests
- 90/90 real-HA tests on HA 2024.11.3 / Python 3.12
- 90/90 real-HA tests on HA 2025.3.4 / Python 3.13
- cited Core and HA CI conclusions

However, evaluator parity did NOT prove complete pipeline parity.

The reviewer found defects in:

- assessment persistence
- concurrent/out-of-order publication
- ingestion isolation
- provider update behavior
- sensitive geometry handling
- evidence provenance
- scheduler backoff
- DB timeout handling
- ID-less record handling
- pipeline parity
- evaluating only current-batch sightings

All items below are now authoritative correction requirements.

==================================================
PRIMARY PRODUCT INVARIANT
==================================================

This must remain true everywhere:

A failure, stale generation, partial pipeline run, database problem, source
problem, or publication race MUST NEVER appear to the user as:

"Nothing worth changing plans for."

A COMPLETE assessment means:

- one internally consistent published generation
- its opportunity items
- its evidence
- its source-input provenance
- its safety/access/condition state

all refer to the same generation.

==================================================
BLOCKER B1
IMMUTABLE ASSESSMENT GENERATIONS
==================================================

Current defect:

An older or concurrent assessment can displace/re-point data belonging to a
newer assessment.

Observed consequences include:

- assessment_state = complete
- items = []

while:

- detail still returns a cant_miss opportunity

and:

- mixed-generation list contents

Concurrent reproduction produced false complete-empty in 10/10 trials.

This is CRITICAL.

Implement immutable assessment generations.

Recommended conceptual model:

assessment_runs

opportunities
    stable occurrence identity registry

assessment_opportunities
    immutable opportunity decision within one assessment generation

assessment_current
    singleton pointer to the currently published assessment

generation-scoped evidence associations

==================================================
ASSESSMENT_RUNS
==================================================

Add/extend:

assessment_runs

with a constrained status model such as:

published
superseded
failed

Also retain:

data_as_of
generated_at
engine_version
definition provenance where applicable

If useful, store a deterministic:

input_fingerprint

representing the normalized logical inputs used for generation.

Do not use random row IDs as semantic generation ordering.

==================================================
ASSESSMENT_CURRENT
==================================================

Add a singleton current pointer.

Conceptually:

assessment_current

id = 1

assessment_run_id FK

Enforce singleton semantics.

Publishing a generation must:

1. begin transaction
2. lock the current pointer row
3. inspect current generation ordering
4. insert the new immutable assessment
5. insert all generation items
6. insert generation evidence
7. insert material revisions
8. atomically advance the pointer if appropriate
9. commit

Older writers must never mutate the current published generation.

==================================================
GENERATION ORDERING
==================================================

Reviewer recommendation was:

strictly newer `data_as_of` advances;
older/equal becomes superseded.

Refine this slightly:

OLDER `data_as_of`:

must NOT advance.

SAME `data_as_of` + SAME deterministic input fingerprint:

treat as idempotent replay/superseded.

SAME `data_as_of` + DIFFERENT input fingerprint:

do NOT silently discard it as an idempotent replay.

Treat this as an explicit conflict/failure condition and preserve diagnostics.

Do not create order-dependent publication behavior.

NEWER `data_as_of`:

may advance if generation completes successfully.

If you determine the existing system has a better monotonic generation
watermark than `data_as_of`, document and justify it.

The central requirement is deterministic monotonic publication.

==================================================
ASSESSMENT_OPPORTUNITIES
==================================================

`opportunities` should represent stable occurrence identity.

Do not re-point an opportunity row between assessment generations.

Use a generation-scoped representation such as:

assessment_opportunities

Conceptually:

assessment_run_id
opportunity_id

presentation
eligibility
significance
confidence
urgency

evidence_state
access_state
safety_state
condition_state

timing
drive state

reason
awaiting

definition key/version/hash
engine version

and whatever typed fields are required to reproduce the API result.

PRIMARY KEY should bind:

assessment_run_id + opportunity_id

or an equivalent strict unique relationship.

Do NOT make arbitrary JSON the only authoritative decision representation.

A serialized product JSON may exist as an explicitly versioned cache if useful,
but typed decision columns remain authoritative.

==================================================
READ CONSISTENCY
==================================================

Both:

GET /api/v1/opportunities

and:

GET /api/v1/opportunities/{occurrence_key}

must resolve ONE current assessment generation.

They must never read different generations.

The list envelope must include:

assessment_id

or an equivalent generation identifier.

Detail must return 404 if the requested occurrence does not exist in the
current generation.

Use an appropriate consistent database snapshot/isolation strategy.

Do not repeatedly resolve the pointer halfway through one logical read.

==================================================
BLOCKER B2
COLLECTION SUCCESS != ASSESSMENT SUCCESS
==================================================

Current defect:

Collection can commit successfully.

Generation can then fail.

Source health remains UP.

The old published assessment remains marked COMPLETE even though newer,
unassessed safety data exists.

Example reproduced:

T:
assessment safe / cant_miss

T+1h:
new High Wind Warning ingested

generation fails

API still reports:
complete
cant_miss
safe

This is unacceptable.

Use TWO truthful transactional stages:

COLLECTION TRANSACTION

then:

GENERATION/PUBLICATION TRANSACTION

Do NOT incorrectly merge everything into one giant transaction.

==================================================
COLLECTION TRANSACTION
==================================================

Collection success should mean:

"We successfully collected and stored this source attempt."

That is legitimate even if subsequent opportunity generation fails.

Collection transaction should atomically include, as applicable:

source_run

raw observations

normalization

accepted/rejected counts

Commit.

Source health is fundamentally collection health.

==================================================
GENERATION TRANSACTION
==================================================

Generation should:

- acquire publication serialization
- evaluate stored current eligible assertions
- create assessment_run
- create assessment opportunities
- create evidence associations
- create material revisions
- publish the pointer atomically

If generation fails:

published generation remains unchanged

AND:

best-effort record a failed assessment_run

Do not corrupt the current generation.

==================================================
ASSESSMENT FRESHNESS / OUTDATED STATE
==================================================

The API must determine whether the currently published generation has been
overtaken by newer REQUIRED or ACTUALLY CONSULTED source data.

Do NOT simply say:

"Any source_run newer than assessment.data_as_of makes the assessment stale."

That would make unrelated source updates degrade unrelated opportunities.

Persist generation source provenance.

Add an explicit generation-scoped association such as:

assessment_sources

Conceptually:

assessment_run_id
source_id
source_run_id
role
required BOOLEAN
consulted BOOLEAN

Exact schema may differ.

This must let Core answer:

- which source runs fed this generation?
- which required sources were expected?
- which safety inputs were used?
- has materially relevant newer input arrived since publication?

If materially relevant required input is newer than the published generation
for longer than the configured evaluation grace period:

assessment_state must NOT remain complete.

Recommended:

degraded

and identify:

degraded_sources

If the newer unassessed source has:

SAFETY

responsibility for the opportunity:

apply conservative HOLD/safety behavior consistent with existing stale-source
semantics.

Test this.

==================================================
BLOCKER B3
BAD-RECORD ISOLATION
==================================================

Current defect:

one future-dated observation can reject an entire otherwise-valid batch.

Legacy handles records individually.

Implement record-level admission/validation.

One bad provider record must not discard unrelated good records.

==================================================
MALFORMED RECORDS
==================================================

Examples:

unparseable timestamp
missing required subject
missing coordinates when the source requires them
non-finite coordinates
otherwise un-normalizable provider record

Preferred behavior:

- retain raw record for diagnostics when identity is sufficient
- create no current normalized assertion
- increment records_rejected
- log sanitized parser failure
- continue processing remaining records

Do not log provider payloads containing sensitive data.

==================================================
FUTURE-DATED RECORDS
==================================================

A record that is slightly future-dated is NOT automatically malformed.

Legacy admission semantics use the evaluation window:

[now - 14 days, now + 1 hour]

for this Tule Elk pipeline.

Therefore:

store the future record

normalize it

count it as accepted if otherwise valid

but exclude it from evidence until evaluation time admits it.

It should become usable later without requiring a provider refetch.

Do not let:

fetched_at

extend:

observed_at

freshness.

==================================================
BLOCKER B4
PROVIDER UPDATE SEMANTICS
==================================================

Current defect:

On repeated `(source_id, external_id)` Core updates essentially only
`fetched_at`.

This causes stale:

timestamps
coordinates
sensitivity
species
counts
payloads

and can produce normalized assertions that disagree with their raw provider
record.

Correct this.

==================================================
RAW OBSERVATION UPDATE MODEL
==================================================

For stable provider IDs, add:

content_sha256

or an equivalent canonical content fingerprint.

Repeated `(source_id, external_id)`:

IF normalized provider content is unchanged:

update observation fetch metadata such as fetched_at/source_run as appropriate.

IF provider content changed:

update current raw record fields such as:

observed_at
exact_geometry
raw_payload
parser_version
fetched_at
source_run_id

and any other authoritative provider fields.

Then re-normalize the record.

Do not create a huge observation revision architecture for M1.

==================================================
NORMALIZED ASSERTION SUPERSESSION
==================================================

Add:

superseded_at TIMESTAMPTZ NULL

or an equivalent current/superseded mechanism.

Current normalized assertions must be identifiable efficiently.

When a provider correction changes the asserted subject:

old assertion becomes superseded

new assertion becomes current

Historical evidence may retain an FK to the superseded assertion.

Current evaluation MUST NOT use superseded assertions.

Use a partial uniqueness constraint where useful to enforce current assertion
identity.

==================================================
UPDATE TEST CASES
==================================================

Correctly support:

same external ID + changed timestamp

same external ID + changed coordinates

same external ID + public -> sensitive

same external ID + sensitive -> public

same external ID + corrected subject/species

same external ID + changed count

same external ID + changed behavior

same external ID + payload-only change

==================================================
SENSITIVITY RULE
==================================================

For AUTOMATED provider updates:

protection is monotonic.

Conceptually:

new_sensitive =
old_sensitive OR provider_sensitive

Automated ingestion may preserve or increase protection.

It must not automatically reveal a previously protected location.

Do NOT add a database invariant that makes sensitivity permanently irreversible.

A future explicitly audited administrator correction may legitimately decrease
protection.

That feature is NOT M1.

==================================================
BLOCKER B5
PRIVATE/SENSITIVE OBSERVATIONS MUST STILL SUPPORT INTERNAL INTELLIGENCE
==================================================

Reviewer found a pipeline parity divergence:

Legacy retains private-location sightings as evidence but never publishes their
location.

Core currently NULLs analysis geometry and skips them.

That changes decisions.

Correct the conceptual geometry separation:

exact_geometry
    provider/raw restricted geometry

analysis_geometry
    internal geometry permitted for intelligence

public_geometry
    geometry safe to leave Core

For this current Tule Elk parity case:

a private/sensitive observation may still have internal analysis geometry.

public_geometry must remain NULL/withheld.

API/HA DTO continues to show only the curated safe public site.

Do NOT expose exact/analysis geometry through API, logs or HA storage.

Future sensitive-species policy may choose a generalized analysis geometry
instead of exact geometry.

Do not create a universal rule that all sensitive records must always use their
exact location internally.

The source/phenomenon policy controls this.

For current legacy parity, retain usable internal analysis geometry.

==================================================
BLOCKER B6
TRUTHFUL EVIDENCE PROVENANCE
==================================================

Current defect:

every supporting sighting can be linked to every opportunity generated in the
run.

Observed example:

2026 sighting marked SUPPORTING for 2027 season row.

Evidence also accumulates forever and is not generation scoped.

This directly violates the architecture.

Fix it in M1.

==================================================
EVALUATOR EVIDENCE OUTPUT
==================================================

The evaluator must identify which normalized observations actually supported
each generated opportunity.

Inputs should carry normalized observation identity.

Opportunity evaluation result should carry evidence IDs used for that decision.

For current Tule Elk behavior:

presence evidence belongs only to the appropriate near occurrence/window.

A distant calendar season row must not inherit a 2026 observation.

Do NOT continue the workaround:

"run evaluator once per sighting and then link everything."

==================================================
GENERATION-SCOPED EVIDENCE
==================================================

Evidence relationship must include the assessment generation.

Conceptual relationship:

assessment_run_id
opportunity_id
normalized_observation_id
disposition

and strict FKs to:

assessment_opportunities
normalized_observations

Disposition:

SUPPORTING
CONTRADICTORY
NEUTRAL

A later generation creates its own evidence set.

The prior generation retains its historical evidence.

No evidence links should be silently carried forward merely because the stable
opportunity identity remains the same.

==================================================
SOURCE/CONTEXT EVIDENCE
==================================================

Also preserve which source run/context actually informed things such as:

safety
access
conditions

Do not connect every current source indiscriminately.

This can use the assessment_sources association described above.

==================================================
OPPORTUNITY REVISIONS
==================================================

Maintain the M1 design goal:

do not record a giant arbitrary snapshot every poll.

Do preserve meaningful decision changes.

A revision should reference the generation item that introduced the material
change.

Material changes can include:

presentation
eligibility
significance
confidence beyond configured threshold
urgency
evidence state
safety
access
conditions
definition version
reason

This lets us answer later:

"What evidence supported this state at that time?"

==================================================
BLOCKER B7
SCHEDULER BACKOFF
==================================================

Fix in M1.

The scheduler framework must guarantee that ordinary collector failures enter
backoff.

Do not catch BaseException.

`CancelledError`, `KeyboardInterrupt`, and `SystemExit` must not be converted
into provider failures.

Collector failures should classify approximately:

TimeoutError
    timeout

aiohttp.ClientResponseError
    http_<status>

other aiohttp.ClientError
    network

OSError
    network

ValueError used for parser failures
    parser_failure

unexpected ordinary Exception such as KeyError
    adapter_failure

All ordinary collector failures must advance backoff.

==================================================
HTTP FAILURE
==================================================

Non-2xx responses are failures.

429/503/etc. must participate in backoff.

Honor Retry-After where valid.

==================================================
RETRY-AFTER
==================================================

Parsing must be safe.

Support:

delta-seconds

HTTP-date

Reject/ignore invalid values such as:

NaN
Infinity
negative numbers
garbage

Past HTTP dates become zero.

Never construct a timedelta from an unbounded provider number.

Add policy:

maximum_retry_after

Default may equal:

maximum_backoff

Current reviewer recommendation:

86,400 seconds

This is reasonable unless the existing scheduler policy clearly establishes
another value.

Clamp BEFORE timedelta/date arithmetic.

Log:

retry_after_clamped

when applicable.

Final delay should respect both:

Core's own backoff

and:

provider Retry-After within configured bound.

==================================================
SCHEDULER STATE STORE FAILURE
==================================================

Current defect:

if scheduler-state persistence fails, each loop reloads the old persisted
value and keeps retrying at minimum interval.

Fix:

load persisted state when task starts.

Maintain authoritative in-process state for the life of the running task.

Persist state best-effort after attempts.

A persistence failure must NOT roll the live state backward.

Log sanitized:

scheduler_failure
code=state_persist_failed

No additional queue infrastructure.

==================================================
REQUIRED FIX N1
DB WRITES BEHIND DATABASE GUARD
==================================================

Move ingestion/database transactions through the existing Database abstraction
and deadline/error-sanitization guard.

Do not let raw SQLAlchemy exceptions escape unsanitized.

Do not leave ingestion transactions unbounded.

==================================================
REQUIRED FIX N2
FROZEN DATABASE TIMEOUT / CONNECTION LEAK
==================================================

Independent review reproduced:

database timeout = 2 s

docker pause DB

8 concurrent requests

7 returned around the deadline

1 hung beyond a 15-second watchdog

and left a checked-out asyncpg connection that was only reclaimed by garbage
collection.

This is NOT optional for final M1 acceptance.

Investigate and fix.

The required invariant:

A frozen/unresponsive database cannot cause an API request to hang materially
beyond the configured DB deadline.

No connection remains leaked/checked-out afterward.

Do not blindly copy a guessed implementation.

Investigate SQLAlchemy + asyncpg cancellation/connection invalidation behavior
and implement the correct mechanism.

Potential direction:

invalidate/terminate timed-out connection without awaiting an unbounded graceful
close

but verify this against the actual stack.

Add R19.

==================================================
REQUIRED FIX N3
CORRUPT STORED PRODUCT
==================================================

Current behavior:

one invalid stored opportunity row:

- makes list API return raw 500 behavior
- readiness remains green

Writes normally validate these rows, so this represents:

direct corruption
schema drift
manual DB modification
unexpected historical data

Do not make readiness scan the whole opportunities table on every call merely to
detect this.

But data routes must fail safely.

Preferred behavior:

sanitized 503

error code such as:

invalid_stored_product

or, only if architecturally justified:

exclude bad row AND mark the assessment degraded

Do NOT silently return a healthy complete partial assessment.

Add a regression test.

==================================================
REQUIRED FIX N4
ID-LESS RECORDS
==================================================

Current fixture source is expected to have stable IDs.

For a source declared to require stable IDs:

ID-less records must be:

rejected
counted
sanitized-log only

They must not create uncontrolled duplicate:

raw rows
normalized assertions
evidence links

Do NOT invent a universal content hash dedup algorithm in M1.

Future sources without IDs may define source-specific canonical fingerprints.

==================================================
REQUIRED FIX N5
PIPELINE PARITY
==================================================

Evaluator-only parity is no longer sufficient.

The original parity harness bypassed legacy:

digest(raw, now, 14d)

and therefore missed:

future timestamp behavior
private sightings
pre-evaluation filtering
legacy grouping behavior

Add PIPELINE LEVEL parity.

The comparison must exercise:

raw fixture
→ ingestion
→ normalization
→ evaluation
→ persistence
→ API

against the equivalent pinned legacy:

digest/fresh
build_seasonal_opportunities
annotate

for the M1 vertical slice.

Include variants:

normal
private/sensitive
future-dated
corrected provider observation

Do not hard-code expected Core output.

==================================================
REQUIRED FIX N6
EVALUATE STORED CURRENT ASSERTIONS
==================================================

Current ingestion evaluates only sightings arriving in the CURRENT batch.

This is wrong for incremental providers.

Example:

Day 1:
valid bear/elk/etc. presence arrives

Day 2:
provider returns only new records

the Day-1 assertion can still be within valid evidence age.

Core must evaluate:

stored CURRENT, non-superseded assertions

that satisfy evaluation admission/freshness rules.

Do not evaluate only:

this fetch's rows.

For the M1 Tule Elk rule, preserve legacy admission:

[now - 14 days, now + 1 hour]

and its behavior cutoff semantics.

==================================================
OPTIONAL / LOW COST N7
STALE HA CACHE NEUTRALIZATION
==================================================

Reviewer found cached stale rows retain:

reason
awaiting
blockers
condition_state

while held/ineligible/safety unknown is applied.

If low risk:

neutralize stateful/current-looking explanatory fields when presenting stale
cache so the UI cannot imply those conditions are still current.

Do NOT destabilize the existing tested HA bridge for cosmetic reasons.

This is lower priority than B1-B7/N1-N6.

==================================================
LOW COST N8
OPERATOR SCRIPT CLEANUP
==================================================

If safe:

backup.sh

should remove `.partial` output on failure using a trap or equivalent.

README should explicitly state that backup/restore scripts requiring Compose
project context are run from the Core repo/Compose directory.

Keep this narrow.

==================================================
MIGRATION 0002
==================================================

DO NOT rewrite migration 0001.

Create:

0002

The upgrade path:

0001 with existing data
→
0002

must be tested.

0002 is expected to include, as required by your final design:

assessment_runs status changes

assessment_current singleton pointer

assessment_opportunities

assessment/source provenance associations

generation-scoped evidence associations

opportunity revision generation-item FK where needed

raw_observations.content_sha256

normalized_observations.superseded_at

partial current-assertion uniqueness

supporting indexes/constraints

Do not add speculative Milestone-2 schema.

==================================================
MIGRATION OF EXISTING M1 DATA
==================================================

Migration must preserve existing:

occurrence_key

stable opportunity identity

relevant M1 data

Do not silently discard existing development data unless explicitly justified
and documented.

R20 must test:

0001 data
→
0002
→
occurrence identity preserved

==================================================
CONDOR Q9
==================================================

Do NOT implement Condor in this correction pass unless it is already present
and needed for existing tests.

The independent review found a LEGACY defect/design weakness:

Condor identity currently includes:

now.date()

This rolls identity daily and can reset Follow/Skip/Seen and notification state
during one continuous spectacle.

Do NOT blindly port this behavior later.

Record a deferred architectural decision:

future Condor occurrence identity should use an EPISODE model similar to the
existing aurora/waves episode concept.

Likely identity basis:

phenomenon
+
site
+
episode_start

where qualifying evidence freshness determines whether the episode continues.

This is not a Milestone-1 implementation requirement.

Document it for the next phase.

==================================================
FULL REGRESSION TEST MATRIX
==================================================

Implement the reviewer's R1-R20 suite.

R1
STALE AFTER NEWER

publish T+1h
then publish T

Current pointer stays T+1h.

T run superseded.

List remains correct.

==================================================
R2
EQUAL TIMESTAMPS
==================================================

Case A:

same data_as_of
same input fingerprint

must be deterministic/idempotent.

Case B:

same data_as_of
different input fingerprint

must NOT silently behave as a replay.

Verify explicit safe behavior.

==================================================
R3
CONCURRENCY
==================================================

Run newer and older writers concurrently repeatedly.

At least 20 iterations.

Current generation always ends at the valid newer generation.

Never complete-empty.

==================================================
R4
GENERATION CONSISTENCY
==================================================

Newer generation with 2 items.

Older generation with 1 item.

List/detail must use the same assessment.

Envelope assessment_id must match.

Detail outside current generation returns 404.

==================================================
R5
BAD RECORD ISOLATION
==================================================

Batch:

valid record
+
T+2h record
+
malformed record

Valid used.

T+2h stored but not yet admitted.

At later evaluation, future record becomes eligible according to legacy window.

Malformed row handled according to record policy and counted rejected.

==================================================
R6
TIMESTAMP CORRECTION
==================================================

Provider timestamp correction in both directions.

Evidence freshness follows provider observed timestamp.

fetched_at never extends evidence life.

==================================================
R7
COORDINATE CORRECTION
==================================================

Update coordinates.

Analysis geometry follows corrected provider state.

Move sufficiently outside current phenomenon radius.

Evidence no longer qualifies.

Reviewer used >120 km in probe; preserve meaningful equivalent based on actual
legacy rule.

==================================================
R8
PUBLIC -> SENSITIVE
==================================================

Observation becomes protected.

Still usable internally where policy permits.

No private geometry in:

Core API
HA payload
logs

==================================================
R9
SENSITIVE -> PUBLIC
==================================================

Automated provider update remains conservatively protected.

No automatic sensitivity decrease.

==================================================
R10
SPECIES/SUBJECT CORRECTION
==================================================

Old normalized assertion superseded and excluded from current evaluation.

New assertion matches current raw provider payload.

R10b:

count change
behavior change if applicable
payload-only change

==================================================
R11
NO CROSS-SEASON EVIDENCE
==================================================

Horizon 366.

2026 evidence must not support a distant 2027 season opportunity unless the
rule actually uses it.

Expected current behavior:

2027 season row gets zero supporting links.

==================================================
R12
EVIDENCE REPLACEMENT
==================================================

Later generation no longer using evidence has no current-generation link.

Earlier generation/revision retains historical provenance.

==================================================
R13
UNEXPECTED EXCEPTIONS BACK OFF
==================================================

At minimum:

KeyError

aiohttp.ClientResponseError

must back off.

R13b:

scheduler state store failure must not cause hammering.

==================================================
R14
ABSURD RETRY-AFTER
==================================================

Test:

1e9

1e12

Must clamp.

No overflow.

==================================================
R15
MALFORMED RETRY-AFTER
==================================================

Test:

nan
inf
-5
garbage
naive HTTP date
past HTTP date

No crash.

Own backoff applies as appropriate.

==================================================
R16
PARTIAL PIPELINE FAILURE
==================================================

Collection commits.

Generation fails.

Verify:

source health can remain UP because collection succeeded

assessment does NOT appear current/complete relative to materially newer data

safety-related newer source causes conservative hold behavior

failed assessment attempt recorded best effort

==================================================
R17
ID-LESS RECORD
==================================================

For stable-ID source:

reject

count rejected

no duplicate raw/current assertions/evidence

==================================================
R18
PIPELINE PARITY
==================================================

Exercise:

ingestion
normalization
stored assertion selection
evaluation
persistence
API

against pinned legacy pipeline semantics.

Include:

private/sensitive
future-dated

variants.

Evaluator decision logic must remain parity-stable.

==================================================
R19
FROZEN DATABASE
==================================================

Pause DB with concurrent requests.

Every request must return bounded failure around:

configured deadline + small allowance

Reviewer suggested deadline + 1 second.

No checked-out connection leak after unpause.

Verify pool recovers.

==================================================
R20
MIGRATION 0001 -> 0002
==================================================

Create real 0001 data.

Upgrade.

Verify:

occurrence keys preserved

schema correct

current generation valid

read API works

==================================================
ADD R21
IRRELEVANT SOURCE UPDATE
==================================================

Required because of the refined assessment-freshness design.

Publish a valid current generation.

Then ingest a newer source run for a source that was:

not required
not consulted
not relevant to the opportunity

The current assessment must NOT become degraded merely because some unrelated
source has newer data.

==================================================
ADD R22
REQUIRED SOURCE UPDATE
==================================================

Publish current generation using a required source.

Commit a materially newer successful run for that source.

Do not publish a new assessment.

After grace period:

assessment_state becomes degraded/outdated.

If SAFETY role:

appropriate opportunity becomes held/conservative.

==================================================
ADD R23
SAME TIMESTAMP DIFFERENT INPUT
==================================================

Two generation attempts:

same data_as_of

different input fingerprint

must produce deterministic explicit handling.

Never silently classify as idempotent replay.

==================================================
PARITY AFTER CORRECTIONS
==================================================

After fixes:

rerun original 15/15 fixture recapture.

It must still match the pinned legacy fixture where intended.

Re-run evaluator differential fuzz.

Expected:

0 evaluator mismatches

unless a specifically approved intentional pipeline difference is documented.

Also run pipeline-level parity.

Do not change evaluator business policy simply to make persistence tests pass.

==================================================
DATABASE ERROR SANITIZATION
==================================================

Continue the established contract:

No raw SQLAlchemy/asyncpg errors in API responses.

No:

DB URL
credentials
SQL statement
stack trace
token

in normal user/API errors.

==================================================
ASSESSMENT ERROR SEMANTICS
==================================================

Do not return:

200 complete []

for:

database error
generation error
stale unassessed required inputs
corrupt current assessment

Use explicit:

degraded
incomplete

or:

503

according to whether trustworthy useful current data exists.

Document the distinction.

==================================================
HEALTH SEMANTICS
==================================================

Maintain:

/health/live

process alive

/health/ready

can serve valid application requests

DB unavailable:

live may remain 200

ready 503

data 503

A single corrupt product row discovered only on query does not require a
full-table integrity scan in readiness.

The affected API request must fail safely/sanitized rather than claim a healthy
complete assessment.

==================================================
DOCKER / COMPOSE ACCEPTANCE
==================================================

The reviewer could NOT independently reproduce the full Core image build
because its session required a proxy CA baked into the image.

Your environment previously had successful CI.

After corrections, YOU must rerun full Compose acceptance at the final SHA if
your environment supports it.

Do not treat the reviewer's environment limitation as a product defect.

Validate:

Core image build

PostGIS startup

migrations

Core readiness

Core restart

DB restart

fresh Core against restored database

operator backup/restore scripts

==================================================
BACKUP / RESTORE
==================================================

Keep:

pg_dump -Fc

Verify actual scripts after migration 0002.

Required:

backup

clean PostGIS target

restore

migration/schema validation

Core startup

readiness

opportunity data

ownership

Use actual scripts, not merely equivalent manual commands.

==================================================
HOME ASSISTANT
==================================================

Do NOT redesign the HA bridge unnecessarily.

Independent review found it fundamentally sound:

- bounded body size
- timeout handling
- redirects disabled
- strict parsing
- payload whitelisting
- no token leakage
- incomplete/degraded does not overwrite cache
- stale cache capped and conservatively held

The main HA corruption risk is that Core currently lies with:

assessment_state = complete

Fixing Core B1/B2 removes that upstream failure.

After Core corrections rerun:

13 Core-client tests

575 portable HA tests

127 card tests

90/90 HA 2024.11.3

90/90 HA 2025.3.4

Do not alter the card unless required by a verified regression.

==================================================
MILESTONE 2 REMAINS FORBIDDEN
==================================================

Still DO NOT add:

DBSCAN
generalized clustering
map
BirdCast
USGS
CDEC
NWPS
CalHABMAP
CoastWatch
Sentinel
GOES
HPWREN
MBARI
vision worker
OpenVINO
Redis
Celery
Kafka
TimescaleDB
new phenomena

This is a CORRECTION PASS.

==================================================
FIX ORDER
==================================================

Recommended order:

1. Scheduler backoff / Retry-After

2. Migration 0002 schema

3. Ingestion transaction + provider updates + sensitivity + bad-record
   isolation

4. Stored-current-assertion evaluation + evidence IDs

5. Immutable generation publishing / assessment pointer

6. Generation-scoped evidence + source provenance

7. Read consistency / outdated/degraded logic

8. DB frozen-timeout connection handling

9. corrupt stored product handling

10. pipeline parity

11. backup/operator cleanup

12. full regression/CI

If implementation dependencies suggest a slightly different order, document it.

Do not mix all corrections into one unreviewable giant change if clean commits
are practical.

==================================================
REVIEW PACKET UPDATE
==================================================

Update:

IMPLEMENTATION_REVIEW_MILESTONE_1.md

Do NOT overwrite history as if the first implementation had been correct.

Add a clear section:

INDEPENDENT REVIEW CORRECTION PASS

Include:

- Claude findings B1-B7
- N1-N8
- accepted/rejected/modified disposition
- implementation performed
- migration 0002
- tests added
- exact results
- any remaining limitation

Explicitly note that Claude independently found the first-pass defects.

==================================================
NEW REQUIRED REVIEW PACKET CONTENT
==================================================

Document:

assessment generation model

assessment_current semantics

equal timestamp behavior

input fingerprint semantics

assessment_sources/source provenance

collection vs generation transaction boundaries

provider correction behavior

superseded normalized assertions

sensitivity behavior

analysis vs public geometry

evidence scoping

scheduler exception classification

Retry-After clamp behavior

DB timeout/pool recovery

pipeline parity

Condor identity deferred decision

==================================================
FINAL ACCEPTANCE BAR
==================================================

Milestone 1 is only ready for final review when:

All original tests pass.

All relevant R1-R23 pass.

Real PostGIS tests pass.

0001 -> 0002 migration passes.

Backup/restore passes.

Full pipeline parity passes.

Original evaluator parity remains intact.

No false:

complete + empty

can be produced by:

out-of-order writers
concurrent writers
generation failure
database failure

Sensitive geometry does not leak.

Valid private observations still participate in internal intelligence where
legacy/current policy requires.

Evidence is truthful and generation scoped.

Scheduler cannot hammer providers after ordinary failure.

Retry-After cannot disable a source for decades or overflow.

Frozen Postgres cannot indefinitely hang Core API requests or leak pool
connections.

HA remains responsive when Core fails.

No M2 work has been introduced.

==================================================
GIT / CI
==================================================

Main only.

Before changes:

record starting SHA.

No force push.

No reviewer branch.

Push normal commits after tests pass.

Run GitHub CI.

Do not declare completion while CI is red.

==================================================
FINAL RESPONSE
==================================================

Return:

1. concise correction summary

2. starting and final Core SHA

3. starting and final HA SHA

4. migration 0002 summary

5. disposition of every:
   B1-B7
   N1-N8

6. exact R1-R23 results

7. original parity result after corrections

8. pipeline parity result

9. Core test counts

10. real PostGIS results

11. HA portable/card/version-matrix results

12. Docker Compose acceptance result

13. backup/restore result

14. CI links/status

15. updated review-packet path

16. every remaining limitation

17. confirmation no Milestone-2 scope was introduced

End EXACTLY with:

READY FOR FINAL INDEPENDENT MILESTONE 1 REVIEW