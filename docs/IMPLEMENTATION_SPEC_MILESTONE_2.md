You are the PRIMARY IMPLEMENTER for:

PHOTOGRAPHY EVENTS CORE
MILESTONE 2 — OBSERVATION INTELLIGENCE & AGGREGATION

This follows a completed and independently accepted Milestone 1.

Read this entire specification before modifying anything.

Do not expand the scope.

Do not add new external source families.

Do not publish a release.

At completion you MUST produce:

IMPLEMENTATION_REVIEW_MILESTONE_2.md

for an independent Claude Code audit.

==================================================
REPOSITORIES
==================================================

Core:

Tmatz27/photography-events-core

Home Assistant:

Tmatz27/Home-assistant-photography-events

Last independently accepted M1 receipts:

Core:
52db568d6b28cc7716c9329be396786906f65072

HA:
f499d8852ae32e71d8e1b97ed641744fc2b1b084

Before editing:

git checkout main
git pull --ff-only

Verify and record the actual starting SHA in each repository.

If origin/main differs from those accepted receipts:

inspect why.

If the difference is not expected/documentation-only M1 follow-up:

STOP and report before making assumptions.

Main-only workflow.

No long-lived feature branches.

==================================================
MILESTONE 1 IS LOCKED
==================================================

Milestone 1 is accepted.

Its major invariants must not regress:

- immutable assessment generations
- assessment_current publication pointer
- generation-consistent list/detail reads
- complete vs degraded/incomplete semantics
- source/run provenance
- provider corrections
- superseded normalized assertions
- sensitive geometry separation
- generation-scoped evidence
- scheduler/backoff
- bounded DB failure
- async HA bridge
- persisted stale cache
- backup/restore
- evaluator parity
- pipeline parity

Do not redesign these without a demonstrated M2 blocker.

==================================================
M2 PRODUCT PROBLEM
==================================================

The current product can receive dozens of observations such as:

Monarch
Monarch
Common Raven
Black Bear
Warbler
Seal
Monarch
...

Those are useful evidence but terrible user-facing product output.

The photographer does NOT want notifications or normal card rows for ordinary
individual wildlife sightings.

Core must transform observations into meaningful patterns.

Target:

RAW PROVIDER RECORDS
        ↓
NORMALIZED ASSERTIONS
        ↓
REPORT IDENTITY / DEDUPLICATION
        ↓
TEMPORAL FILTER
        ↓
SPATIAL CLUSTERING
        ↓
PATTERN EPISODES
        ↓
PHENOMENON MATCHING
        ↓
OPPORTUNITIES
        ↓
WATCHING / CAN'T MISS

Operating principle:

STORE BROADLY
ANALYZE AGGRESSIVELY
DISPLAY VERY NARROWLY

==================================================
KEY SEMANTIC DISTINCTIONS
==================================================

Never conflate:

PROVIDER RECORD COUNT

NORMALIZED OBSERVATION COUNT

INDEPENDENT REPORT COUNT

INDEPENDENT SOURCE COUNT

MAXIMUM SINGLE-REPORT INDIVIDUAL COUNT

These have different meanings.

Example:

12 observations from 8 independent reports across 2 providers

DOES NOT mean:

12 bears

Likewise:

three observers estimate the same flock as:

10
50
100

must NOT produce:

160 birds

For ordinary crowd-sourced reports, expose:

max_single_report_count = 100

not:

estimated_total_animals = 100

unless a future authoritative source has explicit count semantics supporting
that claim.

==================================================
M2 ARCHITECTURAL PIPELINE
==================================================

Provider Data
        ↓
Normalized Assertions
        ↓
Report Groups / Identity
        ↓
Phenomenon-specific Temporal Admission
        ↓
Generation-scoped Spatial Clusters
        ↓
Persistent Pattern Episodes
        ↓
Existing M1 Opportunity Evaluation
        ↓
HA Product Output

Important separation:

REPORT GROUP
identity / deduplication

CLUSTER
mathematical grouping

PATTERN EPISODE
continuing real-world story

OPPORTUNITY
user-facing product decision

Do not collapse these concepts.

==================================================
NO FUZZY AUTO-DEDUPLICATION
==================================================

This is mandatory.

Do NOT automatically merge reports merely because they have:

same species
nearby coordinates
similar time
similar behavior

Two independent photographers may report the same subject at the same place
and time.

That corroboration is valuable.

Automatic independent-report collapse is allowed only with DEFINITIVE identity
evidence.

==================================================
DEDUPLICATION LEVEL 1
==================================================

Same provider + same stable external ID

is already handled by M1 ingestion.

It represents one provider record.

==================================================
DEDUPLICATION LEVEL 2
==================================================

Cross-provider records may be considered the same underlying report only when
a trusted source adapter can establish explicit common origin.

Examples conceptually:

provider B explicitly carries:
origin_provider = iNaturalist
origin_external_id = ABC123

Do NOT merge merely because two providers expose the same unqualified string
ID.

Identity namespace matters.

Canonical origin should therefore be conceptualized as:

origin_namespace
origin_external_id

or an equivalent trusted representation.

==================================================
LEVEL 3 FUZZY MATCHING
==================================================

Not implemented.

Do not auto-merge.

It may eventually be useful to flag:

possible duplicate

for diagnostics.

That does NOT reduce:

independent_report_count

during M2.

==================================================
REPORT GROUP MODEL
==================================================

Implement an abstraction representing one underlying documentation/report
event.

Suggested:

observation_report_groups

observation_report_group_members

Exact names may change if a clearly superior design exists.

A report group may contain:

multiple normalized assertions from one checklist/report

and:

mirrored normalized assertions from another provider when explicit common
origin is established.

A normalized observation may have only ONE CURRENT report-group membership.

==================================================
REPORT GROUP MEMBERSHIP MUST BE CORRECTABLE
==================================================

Do NOT implement Gemini's recommendation:

"once linked, always linked forever"

as an irreversible constraint.

A provider correction or adapter bug could invalidate a cross-provider identity
link.

Membership should support an auditable current/superseded lifecycle.

Historical clusters must retain the exact report-group relationship used when
they were produced.

Potential mechanism:

observation_report_group_members

report_group_id
normalized_observation_id
link_basis
created_at
superseded_at nullable

with a partial uniqueness constraint ensuring:

one CURRENT group membership per normalized observation

Document the exact design.

==================================================
LINK BASIS
==================================================

Record why records were grouped.

Controlled values might include:

provider_identity
explicit_origin_id
manual_future_reserved

Do NOT add fuzzy_similarity as an automatic dedupe basis in M2.

==================================================
BEHAVIOR IS FIRST-CLASS
==================================================

Do NOT reduce normalized behavior to only an uncontrolled TEXT[].

Raw provider behavior text remains in the raw/provider data.

Normalized behavior should use controlled canonical codes.

Examples may include:

presence
feeding
fishing
courtship
rut
mating
pupping
aggregation
migration
roosting
sow_with_cubs
lunge_feeding
breaching

Do not assume this list is scientifically complete.

Use source-controlled behavior definitions.

==================================================
NORMALIZED OBSERVATION BEHAVIORS
==================================================

Implement or migrate toward a structured relationship such as:

normalized_observation_behaviors

normalized_observation_id FK
behavior_code
evidence_strength/confidence if needed
created_at

Exact schema may differ.

Requirements:

- queryable
- constrained
- historically traceable
- one report can assert multiple behaviors
- no behavior inferred merely from presence
- provider correction can supersede/remove behavior

Do NOT invent probabilistic scoring without need.

==================================================
CLUSTER BEHAVIOR SUMMARY
==================================================

Contrary to Gemini's recommendation, retain a structured generation-scoped
cluster behavior summary rather than only:

behavior_summary TEXT[]

We need to answer:

How many independent reports documented fishing?

How many independent sources documented feeding?

Suggested concept:

cluster_behavior_summaries

cluster_id
behavior_code

observation_count
independent_report_count
independent_source_count

This is summarized evidence, not a replacement for underlying provenance.

Underlying cluster_members remains authoritative.

==================================================
TRIGGER FAMILIES
==================================================

Retain the broader policy taxonomy.

At minimum architecture should continue supporting concepts such as:

AGGREGATION_REQUIRED

BEHAVIOR_REQUIRED

COUNT_THRESHOLD

EXCEPTIONAL_PRESENCE

LIVE_CONFIRMATION_REQUIRED

FORECAST_PLUS_CONFIRMATION

Do not reduce everything to DBSCAN.

Examples:

ordinary Common Raven
→ hidden

Bald Eagle presence
→ usually hidden

repeated Bald Eagle fishing
→ potentially meaningful

generic Humpback presence
→ marine activity

explicit lunge feeding
→ behavior evidence

extremely rare credible bird observation
→ can bypass aggregation using EXCEPTIONAL_PRESENCE

==================================================
CLUSTERING POLICY
==================================================

Clustering policy is phenomenon-specific.

Do NOT build a single global:

eps
minpoints
time window

Policy belongs in version-controlled Python/YAML/data classes.

Potential policy fields:

clustering_enabled

clustering_crs

eps_meters

min_independent_reports

minimum_observations

temporal_window

maximum_cluster_diameter_meters

coordinate_uncertainty_limit

episode_continuation_gap

episode_spatial_tolerance

behavior requirements

count requirements

public-location policy

Do NOT encode executable policies as opaque DB JSONB.

==================================================
POLICY PROVENANCE
==================================================

Every persisted cluster must retain enough provenance to reproduce why it
exists.

At minimum:

phenomenon_key
policy_version
policy_hash
engine_version
assessment_run_id
calculated_at

Do not use a cute string like:

monarch_v2_f8a3c

as the only provenance if separate structured fields are clearer.

==================================================
CLUSTERING CRS
==================================================

Canonical storage remains:

EPSG:4326

For Milestone 2 clustering in the current California-centered operating region,
use:

EPSG:3310
NAD83 / California Albers

for projected meter-based cluster calculations unless implementation research
uncovers a concrete technical blocker.

Reason:

M2's actual operational geography is California-centered.

The clustering engine MUST NOT assume this CRS is permanent.

Make:

clustering_crs

a policy/configuration value.

Future broader CONUS expansion may choose another CRS such as EPSG:5070 or a
different strategy.

IMPORTANT:

EPSG:3310 and EPSG:5070 are projected systems with meter units but are not
magically exact equidistant surfaces everywhere.

Do not claim:

5000 projected meters == exact geodesic 5 km everywhere.

Our biological clustering thresholds are approximate anyway.

Do NOT use:

EPSG:3857

for biological distance clustering.

Do NOT perform DBSCAN on EPSG:4326 degree units.

==================================================
TEMPORAL CLUSTERING
==================================================

Use:

phenomenon-specific temporal admission
+
2D spatial clustering

for M2.

Do NOT implement full space-time DBSCAN.

Conceptually:

eligible normalized assertions

WHERE:

observed_at >= evaluation_time - phenomenon_window

and any future-tolerance rule permits the record

THEN:

cluster spatially.

This is easier to understand, reproduce and test than arbitrary weighted
space-time clustering.

==================================================
LOW-PRECISION OBSERVATIONS
==================================================

Coordinate uncertainty must influence cluster eligibility.

For a tight-clustering phenomenon, a report with uncertainty larger than the
clustering neighborhood can create false precision.

Default M2 rule:

If coordinate uncertainty exceeds the phenomenon's configured clustering
precision limit:

do NOT use that observation to determine DBSCAN membership or centroid.

Do NOT throw the observation away.

It may remain:

regional corroboration

if the phenomenon's policy permits that role.

Regional corroboration alone must not magically satisfy a tight aggregation
threshold.

Test this.

==================================================
AREA-LEVEL OBSERVATIONS
==================================================

Some future/existing observations may refer to:

park
refuge
bay
large locality

rather than a precise point.

Do not pretend an area centroid is a precise wildlife position.

M2 should support at least one of:

- exclude from tight clustering but retain regional corroboration
- use explicit area geometry where available
- route to phenomenon/site-level evidence instead of point clustering

Document the adopted behavior.

Do not invent precision.

==================================================
SPATIAL CLUSTERING
==================================================

Use PostGIS:

ST_ClusterDBSCAN

as the initial candidate clustering primitive.

Execute it:

per phenomenon/policy

on temporally eligible observations/report groups.

Do not cluster the entire observation universe with one policy.

==================================================
CLUSTER INPUT UNIT
==================================================

Be deliberate about whether DBSCAN sees:

normalized observations

or:

independent report groups

The analytical significance should be based primarily on independent reports,
not duplicated mirrors.

Preferred design:

choose one representative analysis geometry per independent report for the
subject/phenomenon being clustered.

Do not allow three mirrored provider rows in one report group to provide three
density points.

Document deterministic representative selection.

==================================================
CHAIN-LINK PROTECTION
==================================================

DBSCAN can form a long chain:

A -- B -- C -- D

where each neighbor is close but A and D are too far apart to represent one
useful concentration.

After DBSCAN proposes a cluster, calculate a coherence metric.

Use PostGIS for spatial calculations where practical.

Candidate:

ST_MinimumBoundingRadius(ST_Collect(...))

Persist:

radius_meters

and derive/check:

diameter ≈ 2 * radius

against phenomenon-specific:

maximum_cluster_diameter_meters

Do not automatically accept a chain-linked mega-cluster.

==================================================
WHEN A CANDIDATE CLUSTER FAILS COHERENCE
==================================================

Do NOT invent a complicated recursive clustering algorithm in M2.

Use a deterministic conservative approach.

Permitted options:

1. rerun with a documented stricter eps once

or

2. reject that candidate cluster as incoherent

The chosen behavior must be:

deterministic
policy-controlled
tested

Do not silently turn one incoherent cluster into a confident spectacle.

==================================================
CLUSTERS ARE GENERATION-SCOPED IMMUTABLE ANALYTICAL ARTIFACTS
==================================================

Gemini called clusters ephemeral.

Interpret that semantically, NOT as:

delete/rewrite history every generation.

A cluster:

- belongs to one assessment generation
- is never mutated after publication
- has immutable membership
- may be pruned later according to retention
- has no stable real-world identity
- may be recomputed differently in the next generation

This preserves historical provenance.

Do NOT "wipe and replace" cluster rows that are referenced by historical
episode/opportunity revisions.

==================================================
MIGRATION 0003
==================================================

Create migration:

0003

Do NOT edit:

0001
0002

Expected new schema concepts likely include:

observation_report_groups

observation_report_group_members

normalized_observation_behaviors

observation_clusters

cluster_members

cluster_behavior_summaries

pattern_episodes

pattern_episode_revisions

Potential episode lineage fields/table

Only add what is actually required.

Do not create speculative source-family tables.

==================================================
OBSERVATION_CLUSTERS
==================================================

Conceptually include:

id BIGINT identity PK

assessment_run_id FK NOT NULL

phenomenon_key NOT NULL

pattern_episode_id FK nullable

policy_version
policy_hash
engine_version

centroid_internal GEOMETRY(Point,4326)

radius_meters

observation_count

independent_report_count

independent_source_count

max_single_report_count nullable

window_start
window_end

first_observed_at
last_observed_at

contains_sensitive_evidence BOOLEAN

created_at

Exact names/types may differ.

Do NOT expose centroid_internal through normal public API.

==================================================
CLUSTER_MEMBERS
==================================================

Persist exact provenance.

Conceptually:

cluster_id

normalized_observation_id

report_group_id

Include strict FKs.

Where possible enforce that:

normalized_observation_id

was a member of:

report_group_id

at the time of cluster computation.

Historical membership must survive later provider/report-group corrections.

==================================================
CLUSTER METRICS
==================================================

Persist useful generation facts:

observation_count

independent_report_count

independent_source_count

max_single_report_count

radius_meters

first_observed_at

last_observed_at

Do NOT initially persist:

convex hull
arbitrary polygon footprint
every pairwise distance

unless required for correctness.

Maximum diameter/coherence may be stored if already calculated and useful.

==================================================
ANIMAL COUNTS
==================================================

Never simply sum crowd-sourced reported animal counts across independent
reports.

Use:

max_single_report_count

as a conservative cluster descriptor.

This means:

"the largest single report counted 100"

not:

"there were exactly 100 animals."

Future authoritative counts may introduce typed count semantics such as:

survey_total
official_census
minimum_count

That is deferred.

==================================================
PATTERN EPISODES
==================================================

A cluster is math.

An episode is the persistent real-world story.

Pattern episodes persist across assessment generations.

Conceptual fields:

id BIGINT identity PK

episode_key UNIQUE

phenomenon_key

status

started_at

last_supported_at

ended_at nullable

public_location_id nullable

contains_sensitive_evidence

policy_version/policy_hash

parent_episode_id nullable

merged_into_episode_id nullable

created_at
updated_at

Exact design may vary.

==================================================
EPISODE STATES
==================================================

Internal states may include:

candidate
developing
qualified
ended

These are intelligence states.

User-facing product presentation remains:

planner
watching
cant_miss
held

Do NOT make:

qualified episode == cant_miss

automatically.

Existing M1 gates still apply:

distance
access
safety
conditions
required evidence
etc.

==================================================
EPISODE CREATION
==================================================

A qualifying candidate cluster may:

- start a new candidate/developing episode
- continue an existing episode

according to phenomenon-specific policy.

Episode identity must NOT depend directly on:

current centroid

because the observed activity can move.

==================================================
EPISODE CONTINUATION
==================================================

Evaluate deterministic compatibility based on things such as:

phenomenon_key

subject where applicable

time gap

cluster proximity/overlap

approved geographic region

behavior compatibility

policy-specific continuation thresholds

Do not match solely because two cluster centroids are close.

==================================================
EPISODE ENDING
==================================================

If no qualifying support arrives within the configured continuation gap:

end the episode.

Ended episodes do NOT automatically reopen in M2.

New qualifying activity after the gap:

starts a new episode.

This prevents zombie episodes months later.

==================================================
EPISODE IDENTITY
==================================================

Do not use:

date alone
centroid
current cluster id

as episode identity.

Episode persistence in PostgreSQL is the primary continuity mechanism.

The public/internal episode key must remain stable across:

Core restart
DB restart
new assessment generation

Document how `episode_key` is generated.

It need not be reproducible from an empty database if persistence is the
semantic identity source, but it must never regenerate every evaluation.

==================================================
EPISODE SPLIT / MERGE
==================================================

Do NOT implement Gemini's universal rules verbatim.

Biological meaning differs by phenomenon.

For M2 use conservative deterministic lineage.

ONE EPISODE → MULTIPLE NEW CLUSTERS:

- choose at most one strongest compatible cluster to continue the existing
  episode automatically
- additional qualifying clusters start new episodes
- record:

parent_episode_id

or equivalent split lineage

Do not assign one episode identity to multiple spatially independent active
clusters by default.

MULTIPLE EPISODES → ONE NEW CLUSTER:

- merge only if a policy explicitly permits automatic merge AND compatibility
  is unambiguous
- otherwise keep identity conservative rather than silently erasing an episode

If merged:

losing episode becomes ended

merged_into_episode_id points to survivor

Use deterministic tie-breaking.

Document tie-breaking.

No output may depend on unordered SQL row order.

==================================================
EPISODE REVISIONS
==================================================

Add append-only:

pattern_episode_revisions

or equivalent.

Record MATERIAL changes such as:

status
last_supported_at
public location
aggregate metrics
episode lineage
qualification state
policy version

Each revision should reference:

assessment_run_id

and contributing cluster(s) as appropriate.

Do not write a revision when nothing materially changed.

==================================================
ONE CLUSTER → ONE EPISODE
==================================================

For M2 a phenomenon-specific cluster may belong to:

zero or one pattern episode

Therefore a separate:

pattern_episode_clusters

many-to-many table is not required unless implementation demonstrates a real
need.

Use:

observation_clusters.pattern_episode_id

for current historical association.

Episode revisions provide history.

==================================================
IMPORTANT:
OBSERVATIONS MAY PARTICIPATE IN MULTIPLE PHENOMENON CLUSTERS
==================================================

A normalized observation may legitimately influence:

whale_activity

and potentially:

whale_feeding

depending on explicit behavior evidence.

Therefore:

one observation can participate in multiple clusters belonging to different
phenomenon policies.

Do not globally mark an observation "consumed."

==================================================
PUBLIC LOCATION IS NOT CLUSTER CENTROID
==================================================

This is a hard safety/product rule.

Cluster centroid answers:

"where are these observations mathematically centered?"

It does NOT answer:

"where should the photographer go?"

Never automatically use centroid_internal as:

API location
map pin
navigation point
HA destination

==================================================
CURATED PUBLIC DESTINATIONS
==================================================

Reject Gemini's proposal to simply choose:

nearest location

using ST_ClosestPoint.

Nearest can be:

private
closed
inaccessible
poor viewing
wrong side of terrain
unsafe
biologically inappropriate

Public location must come from an APPROVED relationship.

Use existing:

locations
phenomenon_locations

or extend them minimally.

A phenomenon/policy can define:

approved public destination(s)

and/or:

approved public region

Cluster may qualify a destination only when policy says that relationship is
valid.

If no safe approved destination is applicable:

do NOT invent one.

Potential result:

pattern remains internal

or:

opportunity is suppressed/held

according to policy.

==================================================
SENSITIVE LOCATION FIREWALL
==================================================

Normal APIs/HA must never expose:

exact_geometry

analysis_geometry

cluster centroid

cluster radius

if those fields could expose protected locations.

Pattern/API serializer must explicitly whitelist public-safe fields.

If an episode contains sensitive evidence:

its public geographic identity is:

approved curated location
approved general region
or omitted

depending on policy.

==================================================
METADATA CAN LEAK TOO
==================================================

Coordinates are not the only privacy risk.

A combination such as:

14 eagles
100-meter radius
specific tiny region

can reveal a protected site.

Therefore policy must be able to suppress/generalize:

radius
observation count
behavior detail
specific region

for sensitive phenomena.

Add tests.

==================================================
PUBLIC CLUSTER SUMMARY
==================================================

For non-sensitive phenomena, user-facing summaries may say:

14 observations
9 independent reports
2 sources
4-day window
approximately 4-mile concentration

For sensitive phenomena:

the serializer may expose less.

Do not have one universal public cluster DTO.

==================================================
INITIAL M2 ARCHETYPES
==================================================

Build deterministic policies/fixtures representing several archetypes.

Do NOT claim the test thresholds are biologically final.

The architecture and behavior are under test.

==================================================
ARCHETYPE 1 — MONARCH AGGREGATION
==================================================

Purpose:

high-density spatial concentration

Test:

scattered reports
→ hidden

tight repeated coastal concentration
→ developing pattern

major confirmed aggregation/count evidence
→ stronger pattern

M2 does not need to scientifically calibrate final Monarch thresholds.

==================================================
ARCHETYPE 2 — BLACK BEAR ACTIVITY
==================================================

Purpose:

looser spatial activity cluster + behavior

Test:

single ordinary bear
→ hidden

multiple local independent reports
→ developing activity

no sow/cub behavior
→ never claim cub activity

explicit sow/cub behavior
→ appropriate behavior evidence

Do not convert observation count into bear count.

==================================================
ARCHETYPE 3 — BALD EAGLE FISHING
==================================================

Purpose:

behavior-driven escalation.

Test:

single ordinary eagle
→ hidden

multiple ordinary eagle reports
→ still potentially hidden

repeated explicit fishing behavior
→ developing behavior pattern

concentration + fishing
→ stronger qualifying pattern

==================================================
ARCHETYPE 4 — HUMPBACK ACTIVITY
==================================================

Purpose:

large marine-scale grouping + hard presence/behavior separation.

Test:

many generic humpback observations
→ whale activity pattern

must NOT become:

feeding confirmed

unless explicit feeding/lunge behavior supports that claim.

==================================================
ARCHETYPE 5 — RARE BIRD
==================================================

Purpose:

EXCEPTIONAL_PRESENCE bypass.

A single sufficiently credible exceptional observation may start an episode or
opportunity without DBSCAN.

Do not require aggregation universally.

==================================================
BIOLOGICAL THRESHOLDS
==================================================

Do NOT invent final production-quality scientific thresholds in code comments
and present them as facts.

M2 may use:

fixture policies

conservative provisional policy values

to prove architecture.

Every such value must be clearly marked:

policy/configuration
not ecological fact

If an existing validated project policy already provides a threshold, preserve
it.

==================================================
RECOMPUTE CLUSTERS
==================================================

Every generation:

select CURRENT non-superseded eligible normalized observations

apply phenomenon-specific temporal/precision rules

resolve independent report identity

recompute spatial clusters from scratch

This must be deterministic.

Provider corrections therefore naturally affect next-generation clusters.

Do NOT incrementally mutate cluster memberships.

==================================================
INPUT ORDER MUST NOT MATTER
==================================================

The exact same logical observation set in a different input/database row order
must produce:

same candidate memberships
same metrics
same episode matching outcome
same opportunity result

Add randomized input-order tests.

Never use unspecified SQL ordering as a tie-breaker.

==================================================
LEGACY PLACE GROUPING
==================================================

M1 preserved legacy grouping by:

(species, place)

for parity.

M2 observation intelligence must NOT rely on this grouping.

Place label becomes descriptive metadata.

Use:

geometry
precision
observation time
report identity
phenomenon policy

for new pattern intelligence.

Do not remove the legacy path required for existing M1 parity until the M2 path
is explicitly enabled.

==================================================
FEATURE ACTIVATION / SHADOW MODE
==================================================

Do NOT immediately replace production behavior on the first successful test.

Implement M2 pattern intelligence so it can initially run in:

shadow/developer mode

against deterministic/current observations without altering normal production
opportunity decisions.

This permits:

- cluster inspection
- episode inspection
- parity protection
- false-positive review

After all M2 tests pass and the independent reviewer accepts the engine, the
product-output integration may be enabled within this milestone if it is
clearly gated and validated.

Do not make unreviewed provisional thresholds suddenly generate Can't Miss
notifications.

==================================================
USER-FACING RAW SIGNAL SUPPRESSION
==================================================

The ultimate M2 product requirement remains:

ordinary individual wildlife observations must NOT flood the normal card.

However, implementation should distinguish:

SUPPRESSION

from:

PROMOTION

We may safely stop rendering raw ordinary sightings without automatically
promoting every computed pattern.

Desired normal output:

Monarch aggregation developing — Pismo area

14 observations
9 independent reports
2 sources
4-day window

Awaiting:
confirmed aggregation count

NOT:

Monarch
Monarch
Monarch
...

Raw records remain available to developer/debug tooling.

==================================================
OPPORTUNITY INTEGRATION
==================================================

The normal product API remains:

GET /api/v1/opportunities

Not every opportunity originates from a pattern episode.

Examples such as:

calendar phenomena
astronomy
weather
other existing deterministic opportunities

may remain non-episode opportunities.

Therefore:

DO NOT redesign the opportunity model to require pattern_episode_id on every
opportunity.

Pattern-derived opportunities may reference:

pattern_episode_id

Existing non-pattern opportunities remain valid.

==================================================
PATTERN API
==================================================

A developer/internal endpoint is useful.

Potential:

GET /api/v1/debug/patterns

GET /api/v1/debug/patterns/{episode_key}

Potential cluster diagnostics:

GET /api/v1/debug/clusters

These must:

require authentication

never be consumed by the normal Lovelace card

apply sensitive-location redaction even in ordinary debug API unless an
explicitly separate local-admin mechanism is later designed.

Do NOT expose raw exact sensitive geometry just because an endpoint is named
debug.

==================================================
HA RESPONSIBILITIES
==================================================

HA does NOT perform:

deduplication
clustering
episode matching
behavior aggregation
pattern scoring

Core owns all M2 intelligence.

HA receives product-level opportunities/summaries.

The existing Core bridge must remain async and failure-safe.

==================================================
NO NEW SOURCE FAMILIES
==================================================

Still forbidden in M2:

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
MBARI Ocean Song
new satellite families

Use:

existing observations
deterministic synthetic fixtures
current M1 fixture plumbing

to prove M2.

==================================================
NO MAP
==================================================

Do not implement the map UI.

The schema should support a future map, but:

map implementation
map card UI
routing pins

remain deferred.

==================================================
NO VISION
==================================================

Do not implement:

Intel iGPU
OpenVINO
webcam classifiers
vision worker

Still deferred.

==================================================
M2 ACCEPTANCE SCENARIOS
==================================================

Implement comprehensive tests.

At minimum cover the following.

--------------------------------------------------
A1 SCATTERED MONARCHS
--------------------------------------------------

40 observations scattered over hundreds of miles.

Expected:

no aggregate Watch

no single giant cluster

no raw-card flood

--------------------------------------------------
A2 TIGHT MONARCH CONCENTRATION
--------------------------------------------------

12 observations tightly concentrated over the configured window.

Expected:

one meaningful candidate/developing pattern

not 12 opportunity rows

--------------------------------------------------
A3 SAME PROVIDER RECORD REDELIVERED
--------------------------------------------------

Expected:

one provider/current normalized observation
one independent report

--------------------------------------------------
A4 EXPLICIT CROSS-PROVIDER MIRROR
--------------------------------------------------

Three provider records carry trusted common origin.

Expected:

one independent report
three contributing sources/provider records

--------------------------------------------------
A5 TWO REAL OBSERVERS
--------------------------------------------------

Same subject/time/place neighborhood but no explicit common origin.

Expected:

two independent reports

Never fuzzy-auto-merge.

--------------------------------------------------
A6 CHAIN LINK
--------------------------------------------------

DBSCAN links points through a chain but resulting candidate exceeds configured
coherence diameter.

Expected:

no confident mega-cluster.

Use deterministic reject or documented one-pass stricter policy.

--------------------------------------------------
A7 BEAR ACTIVITY
--------------------------------------------------

Multiple local independent bear reports.

Expected:

one activity pattern.

--------------------------------------------------
A8 BEAR WITHOUT CUBS
--------------------------------------------------

Expected:

never claim cub behavior.

--------------------------------------------------
A9 EXPLICIT SOW/CUB
--------------------------------------------------

Expected:

behavior evidence present and countable by independent reports.

--------------------------------------------------
A10 ORDINARY BALD EAGLE
--------------------------------------------------

One ordinary presence report.

Expected:

hidden.

--------------------------------------------------
A11 BALD EAGLE FISHING
--------------------------------------------------

Repeated explicit fishing behavior.

Expected:

behavioral pattern.

--------------------------------------------------
A12 HUMPBACK PRESENCE
--------------------------------------------------

Generic whale cluster.

Expected:

whale activity only.

Never feeding.

--------------------------------------------------
A13 HUMPBACK FEEDING
--------------------------------------------------

Explicit lunge-feeding reports.

Expected:

feeding behavior evidence.

--------------------------------------------------
A14 EPISODE CONTINUATION
--------------------------------------------------

Next-generation compatible cluster within continuation gap.

Expected:

same episode ID.

--------------------------------------------------
A15 EPISODE END / RESTART
--------------------------------------------------

Evidence gap exceeds policy.

Expected:

old episode ended.

Later activity creates a new episode.

Never reopen ended episode automatically.

--------------------------------------------------
A16 SENSITIVE CLUSTER
--------------------------------------------------

Expected:

analysis can succeed internally.

No exact/analysis/centroid geometry leaks.

--------------------------------------------------
A17 CENTROID ON PRIVATE/INVALID LOCATION
--------------------------------------------------

Expected:

centroid is not used as destination.

Only approved curated public location may surface.

--------------------------------------------------
A18 EXPIRING EVIDENCE
--------------------------------------------------

All support ages out.

Expected:

cluster disappears next generation.

Episode transitions appropriately.

No ghost evidence.

--------------------------------------------------
A19 PROVIDER REMOVES BEHAVIOR
--------------------------------------------------

Correction withdraws fishing/cub/etc.

Expected:

recomputed cluster/episode no longer claims behavior.

Historical revision retains old provenance.

--------------------------------------------------
A20 RARE BIRD
--------------------------------------------------

Single credible exceptional observation.

Expected:

EXCEPTIONAL_PRESENCE path can bypass DBSCAN.

--------------------------------------------------
A21 CORE RESTART
--------------------------------------------------

Active episode retains stable identity.

--------------------------------------------------
A22 DETERMINISM
--------------------------------------------------

Same logical inputs repeatedly.

Expected:

same cluster memberships/metrics and same episode outcome.

--------------------------------------------------
A23 RAW FLOOD
--------------------------------------------------

Large raw observation set.

Expected:

normal HA/product output remains small.

--------------------------------------------------
A24 THREE-PROVIDER MIRROR
--------------------------------------------------

Expected:

one report, not three.

--------------------------------------------------
A25 HIGH UNCERTAINTY
--------------------------------------------------

Observation uncertainty exceeds clustering precision policy.

Expected:

excluded from tight DBSCAN.

May remain regional corroboration.

Does not affect centroid.

--------------------------------------------------
A26 AREA-LEVEL OBSERVATION
--------------------------------------------------

Refuge/park-level location.

Expected:

does not masquerade as a precise point.

Handled according to configured regional evidence policy.

--------------------------------------------------
A27 TWO CLUSTERS APPROACH
--------------------------------------------------

Expected:

deterministic episode behavior.

No identity based on row ordering.

--------------------------------------------------
A28 EPISODE SPLIT
--------------------------------------------------

One episode's next generation produces two independently coherent clusters.

Expected:

strongest compatible cluster may continue parent.

Additional qualifying cluster starts new child episode.

Lineage recorded.

--------------------------------------------------
A29 COORDINATE CORRECTION
--------------------------------------------------

Provider moves an observation between spatial groups.

Expected:

next-generation clustering reflects new position.

Historical generation unchanged.

--------------------------------------------------
A30 ALL SUPPORT EXPIRES
--------------------------------------------------

Expected:

episode ends according to continuation policy.

--------------------------------------------------
A31 HIGH-UNCERTAINTY CORROBORATION
--------------------------------------------------

High-uncertainty record excluded from DBSCAN but retained as regional
corroboration where policy permits.

--------------------------------------------------
A32 COUNT INFLATION
--------------------------------------------------

Three independent reports estimate one flock as:

10
50
100

Expected:

max_single_report_count = 100

NOT:
160

NOT:
"exactly 100 animals"

--------------------------------------------------
A33 REPORT-GROUP CORRECTION
--------------------------------------------------

An explicit cross-provider origin mapping is later corrected/withdrawn.

Expected:

current report membership can be superseded.

Next generation recalculates independent_report_count.

Historical clusters retain previous grouping provenance.

--------------------------------------------------
A34 NO APPROVED PUBLIC DESTINATION
--------------------------------------------------

Strong sensitive cluster exists.

No approved safe public location/region applies.

Expected:

Core does NOT select nearest arbitrary location.

Pattern remains internal or opportunity is suppressed/held per policy.

--------------------------------------------------
A35 INPUT ORDER RANDOMIZATION
--------------------------------------------------

Shuffle identical observation inputs repeatedly.

Expected:

identical logical cluster and episode results.

--------------------------------------------------
A36 POLICY HASH
--------------------------------------------------

Change clustering policy version/hash.

Expected:

new generation records new policy provenance.

Historical cluster retains old provenance.

Episode continuation follows explicitly defined compatibility behavior.

--------------------------------------------------
A37 SENSITIVE METADATA REDACTION
--------------------------------------------------

Sensitive episode has:

tight radius
specific count
small named region

Expected:

public serializer suppresses/generalizes fields according to policy.

No indirect location leak.

--------------------------------------------------
A38 NON-PATTERN OPPORTUNITY
--------------------------------------------------

Existing deterministic M1 opportunity.

Expected:

continues working with no pattern_episode_id.

M2 does not force every opportunity through pattern engine.

==================================================
MIGRATION TESTS
==================================================

Test:

0001
→
0002
→
0003

using realistic existing development data.

Also test:

fresh empty DB
→
0003

Remember accepted M1 operational note:

No real production database currently exists.

Production deployment should begin with a fresh schema at current migration.

Do not spend large amounts of code trying to perfectly rehabilitate every
quirk from temporary 0001 development data.

But migrations themselves must remain valid.

==================================================
M1 REGRESSION
==================================================

All M1 tests must remain green.

At minimum rerun:

Core suite
real PostGIS suite
legacy parity
pipeline parity
18,000 evaluator fuzz or equivalent existing deterministic command
HA Core-client tests
HA portable tests
card tests
real HA matrix where CI already supports it

Do not break M1 to implement M2.

==================================================
PERFORMANCE
==================================================

M2 scale is modest.

Do not introduce:

Redis
Celery
Kafka
materialized distributed jobs
machine-learning infrastructure

PostgreSQL/PostGIS + Python are sufficient.

Nevertheless:

avoid obvious N+1 queries

use GiST indexes

index current report memberships

index assessment-run cluster queries

batch cluster persistence

measure representative query performance

Document query plans for the primary clustering query if practical.

==================================================
EXPECTED INDEXING
==================================================

Review actual query patterns.

Likely needs include:

GiST:
normalized observation analysis geometry
cluster internal centroid if queried spatially
approved location/region geometry

B-tree/partial:
current report-group membership
report group origin identity
cluster assessment_run_id
cluster phenomenon_key
cluster pattern_episode_id
episode status
episode phenomenon_key
episode last_supported_at
behavior observation relationships

Do not mechanically add every possible index.

==================================================
POLICY SOURCE CONTROL
==================================================

All clustering/episode behavior policy remains source-controlled.

Do not let database rows become the authoritative logic.

Persist:

policy_version
policy_hash

with outputs.

The policy hash must be deterministic from canonical policy contents.

Add a test proving identical policy produces identical hash independent of
dictionary/key ordering where applicable.

==================================================
LOGGING
==================================================

Add structured event codes for meaningful M2 diagnostics.

Examples:

report_group_created
report_group_membership_superseded
cluster_created
cluster_rejected_incoherent
cluster_low_precision_excluded
episode_created
episode_continued
episode_split
episode_merged
episode_ended
public_location_unavailable

Do not log exact sensitive coordinates.

==================================================
DEBUGGING / OBSERVABILITY
==================================================

The independent reviewer must be able to answer:

Why was this observation counted as report #7?

Why were these points clustered?

Why was a point excluded?

Why did this cluster continue episode X?

Why did episode X end?

Why didn't this pattern become an opportunity?

Provide inspectable provenance.

Do not create opaque "AI score" behavior.

==================================================
IMPLEMENTATION PHASING INSIDE M2
==================================================

Recommended order:

PHASE 2A
Schema + identity

- migration 0003
- report groups
- group membership
- behavior assertions
- provenance

PHASE 2B
Deterministic clustering

- temporal admission
- uncertainty filtering
- EPSG:3310 transform
- ST_ClusterDBSCAN
- coherence guard
- cluster membership
- metrics
- behavior summary

PHASE 2C
Episodes

- creation
- continuation
- ending
- deterministic split/merge lineage
- revisions

PHASE 2D
Opportunity adapter

- pattern → opportunity
- safe public destination
- sensitive summary redaction
- exceptional-presence bypass

PHASE 2E
Shadow integration

- compute against current/test observations
- debug inspection
- no provisional thresholds causing production notifications

PHASE 2F
Product suppression

- ordinary raw wildlife/background observations no longer appear individually
  in normal product output
- qualified pattern summaries replace them

Do not skip directly to 2F before the earlier phases are tested.

==================================================
MANDATORY REVIEW PACKET
==================================================

Create/update:

IMPLEMENTATION_REVIEW_MILESTONE_2.md

This is specifically for an independent Claude Code reviewer.

It must include:

# 1 EXECUTIVE SUMMARY

# 2 REPOSITORY RECEIPTS

starting/final SHAs for both repos

# 3 ARCHITECTURE ACTUALLY IMPLEMENTED

# 4 DEVIATIONS FROM THIS PROMPT

# 5 MIGRATION 0003

Every table/column/constraint/index.

# 6 REPORT IDENTITY MODEL

Explain:

same provider
explicit cross-provider origin
no fuzzy auto-merge
membership corrections

# 7 BEHAVIOR MODEL

# 8 CLUSTER POLICY MODEL

# 9 CRS

Exact SRID used and why.

# 10 CLUSTER QUERY

Explain actual PostGIS operations.

# 11 LOW-PRECISION HANDLING

# 12 COHERENCE / CHAIN-LINK PROTECTION

# 13 CLUSTER IMMUTABILITY / GENERATION SCOPE

# 14 CLUSTER PROVENANCE

# 15 CLUSTER METRICS

# 16 ANIMAL COUNT SEMANTICS

Explicitly confirm no naive SUM.

# 17 EPISODE MODEL

# 18 EPISODE IDENTITY

# 19 EPISODE CONTINUATION

# 20 EPISODE ENDING

# 21 SPLIT/MERGE LINEAGE

# 22 EPISODE REVISIONS

# 23 SENSITIVE LOCATION PROTECTION

# 24 PUBLIC DESTINATION SELECTION

Explicitly confirm no arbitrary nearest-location fallback.

# 25 POLICY VERSION/HASH

# 26 PROVIDER CORRECTIONS

# 27 SHADOW MODE

# 28 PRODUCT SUPPRESSION

# 29 API CHANGES

# 30 HA CHANGES

# 31 ACCEPTANCE TESTS A1-A38

For every scenario:

test name
input
expected
actual
result

# 32 M1 REGRESSION RESULTS

# 33 DATABASE TEST RESULTS

# 34 PERFORMANCE / QUERY PLAN

# 35 SECURITY / PRIVACY REVIEW

# 36 KNOWN LIMITATIONS

# 37 DEFERRED WORK

Explicitly confirm no:

new source families
map
vision
fuzzy dedupe
ML
Redis/Celery/etc.

# 38 QUESTIONS FOR CLAUDE

List anything deserving adversarial review.

# 39 NEXT MILESTONE RECOMMENDATION

Do not implement it.

==================================================
INDEPENDENT REVIEW TARGETS
==================================================

Assume Claude Code will specifically attempt to break:

dedup identity
group correction
count semantics
input-order determinism
DBSCAN chaining
low-precision handling
policy provenance
episode identity
episode split/merge
provider corrections
sensitive metadata leaks
public-location selection
M1 generation consistency
HA suppression
migration 0003

Write code and packet accordingly.

==================================================
NO RELEASE
==================================================

Do not:

tag
publish
create GitHub release
make M2 production-default
announce thresholds as biologically validated

This implementation remains subject to independent review.

==================================================
FINAL RESPONSE
==================================================

Return:

1. concise implementation summary

2. starting/final Core SHA

3. starting/final HA SHA

4. migration 0003 summary

5. report identity implementation

6. behavior implementation

7. clustering implementation

8. CRS used

9. episode implementation

10. sensitive-location/public-destination behavior

11. A1-A38 result summary

12. M1 regression results

13. real PostGIS test results

14. HA test results

15. CI status/links

16. review packet path

17. all known limitations

18. exact features still deferred

19. confirmation M2 is not released

End EXACTLY with:

READY FOR INDEPENDENT MILESTONE 2 REVIEW