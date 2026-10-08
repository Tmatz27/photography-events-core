You are the PRIMARY IMPLEMENTER for:

PHOTOGRAPHY EVENTS CORE
MILESTONE 3A — FIRST LIVE SOURCE CONTRACTS

and the first SHADOW-ONLY portion of:

MILESTONE 3B — PHENOMENON CALIBRATION

This specification reconciles:

- the accepted M1 architecture
- the accepted M2 observation-intelligence architecture
- Gemini's M3 live-source research
- independent verification of current provider documentation

Read everything before modifying code.

Do NOT broaden scope.

Do NOT promote M2/M3 to production opportunity decisions.

Do NOT publish a release.

==================================================
ACCEPTED BASELINE
==================================================

Core last independently accepted H3 tip:

c641596

HA:

c76726e

Verify origin/main before editing.

Record actual starting SHAs.

Main-only workflow.

Milestone 1 remains locked.

Milestone 2 remains locked except where a real live-adapter contract requires a
narrow extension.

Current state:

M1 CLOSED = YES

M2 ENGINEERING CLOSED = YES

M2 SHADOW SAFE = YES

LIVE-ADAPTER ENGINEERING READY = YES

PRODUCTION PROMOTION READY = NO

==================================================
M3 OBJECTIVE
==================================================

M3 moves from deterministic fixtures to real public data.

The goal is NOT:

"connect every API."

The goal is:

define truthful source contracts
+
implement a very small first live-source slice
+
prove malformed-data isolation
+
prove corrections
+
prove privacy
+
measure real volume
+
feed M2 shadow intelligence safely

The epistemic pipeline remains:

SOURCE FACT
    ↓
NORMALIZED ASSERTION
    ↓
M2 PATTERN
    ↓
PHENOMENON POLICY
    ↓
OPPORTUNITY

These layers must remain distinguishable.

==================================================
FIRST M3A LIVE SOURCE SLICE
==================================================

Implement:

1. iNaturalist
   first NEW biological observation adapter

2. WFIGS / NIFC current wildfire data
   first NEW structured safety adapter

3. NWS
   formalize the existing NWS source under the new Source Contract model;
   do not rewrite working NWS behavior merely to call it new

Do NOT implement eBird yet.

Do NOT implement GBIF.

Do NOT implement BirdCast.

Do NOT implement marine or satellite sources yet.

==================================================
SOURCE CONTRACT MODEL
==================================================

Create a source-controlled Source Contract representation.

Prefer typed Python/dataclass/Pydantic/config structures rather than executable
logic hidden in DB JSONB.

Every live source must define at least:

source_key

provider_name

dataset/interface

source roles

authentication type

polling policy

rate-limit policy

pagination model

record identity model

correction/update model

deletion model where available

observation/model timestamp semantics

provider update timestamp semantics

location representation

location precision semantics

geoprivacy semantics

count semantics

behavior semantics

quality/validation fields

freshness policy

malformed-record policy

proof boundaries

retention policy

schema/parser version

Do not require every source to populate fields that do not apply.

==================================================
PROOF BOUNDARIES
==================================================

Every source contract must explicitly define:

CAN_PROVE

CANNOT_PROVE

The adapter may never silently elevate a provider signal beyond those
boundaries.

==================================================
L1 FIX — REQUIRED FIRST
==================================================

Independent M2 verification found one remaining low-severity legacy issue:

a stored row with:

"external_id": null

can cause metadata validation to raise and abort an entire shadow reconcile.

Fix this before live adapters.

At minimum:

if not payload.get("external_id"):
    use the existing deterministic fallback where valid

More importantly:

reconcile must isolate per-record identity/metadata failures.

One bad row must:

- be skipped for the affected identity operation
- emit sanitized `identity_invalid` or equivalent
- increment appropriate rejection/diagnostic state
- allow all other valid rows to continue

Never log:

raw provider payload
private coordinates
API credentials
PII

Add regression coverage for:

legacy external_id NULL

malformed identity

invalid metadata

one bad + many good rows

==================================================
INATURALIST OFFICIAL INTERFACE
==================================================

Use:

https://api.inaturalist.org/v1

public observation retrieval.

Do not scrape HTML.

Public read operations normally do not need authenticated private-coordinate
access.

Photography Events must NOT request hidden/private coordinates.

Use a descriptive User-Agent.

==================================================
INATURALIST RATE POLICY
==================================================

Official iNaturalist documentation states:

hard throttle maximum:
100 requests/minute

recommended operating rate:
approximately 1 request/second / <=60 per minute

recommended daily ceiling:
around 10,000 requests/day

Use the RECOMMENDED limits.

Do not schedule at 100/minute merely because it is technically allowed.

Honor:

429

Retry-After when present

existing Core scheduler/backoff semantics

Use efficient pagination and maximum useful page size.

The official API supports up to 200 observations per page.

Do not fetch one observation per HTTP request when list responses already
contain required fields.

==================================================
INATURALIST QUERY SCOPE
==================================================

This is NOT a bulk-data collector.

Initial M3 taxa only:

Black Bear / relevant Ursus taxon lineage

Monarch butterfly / Danaus plexippus

Do NOT add Humpbacks yet.

Do NOT pull every observation in California.

Use geographically bounded and taxon-bounded requests appropriate to the
project's curated travel region.

Keep query geometry/config source-controlled.

Do not hard-code a giant California scrape.

==================================================
INATURALIST IDENTITY
==================================================

iNaturalist observations expose:

numeric observation ID

and:

UUID

Use a documented stable source external identity.

Prefer the observation UUID if inspection confirms it is consistently exposed
by the chosen endpoint.

Retain numeric provider ID as provider metadata if useful.

Do NOT synthesize identity from:

time
species
coordinates

when a provider identity exists.

==================================================
INATURALIST CORRECTIONS
==================================================

Provider observations may change:

taxon
observed timestamp
coordinates
geoprivacy
quality grade
description/tags
other normalized fields

Use provider update metadata supported by the chosen API.

Do not assume an `updated_since` parameter name without verifying the official
OpenAPI contract.

Implement polling/incremental behavior from the ACTUAL supported search
parameters.

Provider corrections must flow through existing M1/M2:

raw record update
normalized assertion supersession/current state
M2 recomputation

==================================================
INATURALIST TIMESTAMPS
==================================================

Use provider observation time for evidence time.

Prefer a full provider observation timestamp when present.

If only an observation DATE is available:

store that actual precision.

Do NOT invent noon/midnight and pretend it is a precise observation time.

Maintain separately:

observed_at

provider_updated_at

fetched_at

FETCH TIME MUST NEVER RENEW EVIDENCE.

Normalize valid full timestamps to UTC internally.

Retain source timezone/precision metadata when necessary for provenance.

==================================================
INATURALIST GEOPRIVACY
==================================================

Do NOT infer geoprivacy only from an arbitrary positional-accuracy threshold.

Use provider fields such as:

coordinates_obscured

geoprivacy

taxon_geoprivacy

public_positional_accuracy

or their current v1 equivalents.

Official iNaturalist behavior:

OPEN:
public point represents provider's public observation coordinate.

OBSCURED:
public coordinate is a randomized point inside a 0.2° x 0.2° cell containing
the hidden location.

PRIVATE:
true coordinates are not publicly exposed.

Photography Events must NEVER treat the obscured random point as the hidden
true location.

==================================================
SPATIAL BASIS
==================================================

Add/retain enough provenance to distinguish spatial basis.

Conceptually:

open_point

obscured_cell

private_unavailable

area_only

Do not call an obscured public point:

exact_geometry

in product semantics.

The raw provider geometry may still be stored as the provider-returned public
coordinate with its provider geoprivacy metadata.

For M2 tight DBSCAN:

OPEN + acceptable positional accuracy:
may provide analysis geometry.

OBSCURED:
must NOT provide a precise DBSCAN point.

It may serve as regional/site corroboration where policy explicitly permits.

PRIVATE/NO PUBLIC GEOMETRY:
no point clustering.

==================================================
PUBLIC GEOMETRY
==================================================

Raw iNaturalist observation locations do not become HA destinations.

Normal product output continues using:

approved curated locations
approved public regions

Never expose:

raw exact/public observation coordinate
obscured random point as destination
cluster centroid

==================================================
INATURALIST COUNTS
==================================================

Do NOT invent individual counts from ordinary iNaturalist observations.

Initial contract:

presence = true

reported_count = NULL

unless a clearly identified typed source field supplies a trustworthy numeric
count with documented semantics.

Do NOT parse random prose into an animal count.

Do not SUM iNaturalist observations into animal totals.

==================================================
INATURALIST BEHAVIOR
==================================================

Do NOT treat generic descriptions, tags, or arbitrary Observation Fields as
authoritative behavior confirmation.

iNaturalist controlled annotations are useful only for the controlled concepts
they actually represent.

General feeding/fishing/sow-with-cubs behavior is not a standardized provider
fact.

For this first slice:

provider presence:
usable

controlled annotation where semantically relevant:
usable according to its actual meaning

arbitrary text behavior parser:
SHADOW EXPERIMENT ONLY or DEFERRED

It must NOT establish:

BEHAVIOR_CONFIRMATION

for a production phenomenon.

Do NOT build production regex:

"cub"
"feeding"
"fishing"

and call that confirmed behavior.

==================================================
INATURALIST QUALITY
==================================================

Persist source quality fields such as:

quality_grade
community taxon / relevant taxon identity
geoprivacy state

Define roles conservatively.

Suggested initial policy:

Research Grade:
may contribute stronger confirmation/corroboration.

Needs ID / lower confidence:
DISCOVERY or WATCH_SIGNAL only unless phenomenon policy explicitly permits more.

Do not pretend community validation proves behavior.

==================================================
INATURALIST MALFORMED RECORD ISOLATION
==================================================

Every record is parsed independently.

Malformed record examples:

missing UUID/ID

invalid observed time

invalid coordinate

non-finite coordinate

unknown required taxon structure

invalid geoprivacy

malformed count

Expected:

good records survive

bad record rejected

source run records:
received
accepted
rejected

sanitized diagnostic event

No provider payload dump to logs.

==================================================
WFIGS / NIFC
==================================================

Use the official public NIFC ArcGIS FeatureServer.

Initial dataset:

CURRENT WFIGS / Interagency Fire Perimeters

Machine formats include:

JSON
GeoJSON
PBF

Use documented current/working incident data.

Do not scrape maps.

==================================================
WFIGS IDENTITY
==================================================

Inspect and use stable incident identity fields such as:

IRWIN ID
Global ID

according to the actual current layer schema.

Do NOT use:

incident name alone

as identity.

OBJECTID may be retained as layer metadata but should not automatically become
cross-refresh incident identity if a stronger stable ID exists.

==================================================
WFIGS ROLES
==================================================

Initial roles:

SAFETY

possibly CONDITION

NOT:

ACCESS confirmation

A fire perimeter does not prove a road is closed.

Caltrans will later own highway access/closure evidence.

WFIGS may cause:

unsafe / held

when a curated destination itself intersects an active wildfire perimeter
according to the agreed safety rule.

Do not claim road closure from WFIGS alone.

==================================================
WFIGS FIRE TYPES
==================================================

Distinguish at minimum:

wildfire

prescribed fire

where the provider supplies that distinction.

Do not treat a prescribed burn as equivalent to an uncontrolled wildfire
without policy support.

Also distinguish:

current working perimeter

historic/final perimeter

Do not allow a historical perimeter to permanently hold an opportunity unsafe.

==================================================
WFIGS SPATIAL POLICY
==================================================

For M3A shadow validation:

If an approved curated public destination geometry intersects a current
qualifying wildfire perimeter:

safety signal = unsafe/hold candidate.

Do NOT invent a universal arbitrary mile buffer in this pass.

Nearby-but-not-intersecting fire may be recorded as context but is not
automatically unsafe until a future researched policy exists.

No route-closure inference.

==================================================
NWS SOURCE CONTRACT
==================================================

Do not rewrite the existing working NWS integration unnecessarily.

Formalize/document its Source Contract.

Official API:

api.weather.gov

requires a descriptive User-Agent.

No paid API key.

Rate limit is dynamic/not publicly fixed.

Existing retry/backoff must remain.

Roles:

CONDITION
SAFETY

Possible facts:

alerts
forecast conditions
wind
cloud cover
temperature

NWS cannot prove:

microclimate at a specific tree grove
actual monarch clustering
actual wildlife behavior

==================================================
NWS + MONARCH TEMPERATURE
==================================================

Do not encode:

temperature < 55°F
=
monarch aggregation confirmed

Official monarch guidance supports approximately 55°F as an important flight
threshold.

Use temperature only as:

PHOTOGRAPHIC CONDITION

once overwintering/grove activity is otherwise supported.

Conceptually:

cool morning / below flight threshold:
more likely butterflies remain tightly clustered

warmer sunny period:
more likely basking/flying activity

Both can be photographically useful.

Do not make 55°F a universal Can't Miss eligibility rule.

==================================================
M3B SHADOW PHENOMENON 1:
BLACK BEAR ACTIVITY
==================================================

Use iNaturalist only for:

presence
spatial activity
temporal activity
quality/corroboration

Initial M3 shadow ladder:

individual credible presence
→ SIGNAL

multiple independent spatial/temporal reports
→ DEVELOPING ACTIVITY PATTERN

Do NOT claim:

sow/cubs
feeding
foraging

from unstructured iNaturalist text as confirmed behavior in this slice.

Do NOT convert:

report count
into:
bear count

No production thresholds yet.

Use provisional fixture/policy values marked explicitly:

PRODUCT POLICY UNDER CALIBRATION
NOT ECOLOGICAL FACT

==================================================
M3B SHADOW PHENOMENON 2:
MONARCH AGGREGATION
==================================================

Use:

iNaturalist presence
+
spatial relation to curated overwintering grove/site
+
pattern aggregation
+
NWS condition context
+
WFIGS safety

Initial evidence:

individual presence
→ SIGNAL

multiple credible reports associated with an approved overwintering area
→ DEVELOPING AGGREGATION SIGNAL

NWS cool-morning conditions
→ CONDITION modifier

WFIGS destination intersection
→ SAFETY hold

iNaturalist alone MUST NOT elevate this to a fully confirmed major overwintering
count.

==================================================
MONARCH SEASON
==================================================

Do NOT hard-code:

Nov 1 – Feb 28

as the only relevant window.

Western Monarchs can arrive at California overwintering sites in September or
October.

The user specifically wants arrival signals.

Use the project's existing planning context or a broader source-controlled
season that allows arrival tracking.

Do not invent final date gates in this pass.

==================================================
MONARCH CONFIRMATION GAP
==================================================

Record an explicit M3 backlog requirement:

Production Monarch qualification needs a stronger grove/count confirmation
source.

Candidate:

Western Monarch Count / Xerces or another verified dated grove-count source.

Do NOT invent an API.

Do not scrape it in M3A.

Research machine access separately before promotion.

Until then:

iNaturalist-driven Monarch output remains:

WATCH / developing

not definitive major aggregation confirmation.

==================================================
SOURCE FACT VS CORE INTERPRETATION
==================================================

Persist enough provenance to distinguish:

SOURCE FACT:
"iNaturalist reported Danaus plexippus at public coordinate X on date Y"

from:

CORE INTERPRETATION:
"multiple reports form a coastal grove activity pattern"

from:

PHENOMENON POLICY:
"this pattern is sufficient for Watching"

Do not serialize Core inference as if the provider said it.

==================================================
eBIRD — EXPLICITLY DEFERRED
==================================================

Do NOT implement eBird in this slice.

Record these corrections for the future contract:

- API key required for public API
- recent-observation endpoints expose checklist/submission identity such as
  `subId`
- exact occurrence identity must be verified endpoint-by-endpoint
- do not assume `obsId`
- `X` means presence with count unknown
- NEVER convert `X` to count 1
- store:
  presence = true
  reported_count = NULL

Future eBird work must verify:

checklist identity
species occurrence identity
private-location semantics
review/provisional status
comments availability
terms

before coding.

==================================================
GBIF — DO NOT IMPLEMENT
==================================================

Do not ingest GBIF live in M3A.

iNaturalist itself distributes Research Grade observations through GBIF.

eBird also publishes an observational dataset through GBIF.

Using originals + GBIF risks duplicate evidence.

GBIF may be useful later for:

historical research
discovery
offline backfill

but not the first live observation feed.

==================================================
RETENTION
==================================================

Reject the blanket Gemini recommendation:

monthly partition immediately
normalized observations delete after 90 days

Do NOT partition raw_observations in this milestone solely on speculation.

Do NOT purge normalized observations at 90 days automatically.

For M3A:

measure actual source volume.

Continue application retention framework.

Provisional:

raw payload:
source-specific short retention, likely 30–90 days

normalized assertion:
retain long enough for historical/pattern analysis; no new destructive policy
yet

pattern episodes/opportunities:
long-term

source runs:
bounded operational retention

Make final retention policy after real live-volume measurements.

==================================================
LIVE VOLUME MEASUREMENT
==================================================

Gemini's claim:

<1,000 observations/day

is NOT an accepted architectural fact.

Measure it.

During shadow operation record per-source:

requests/day

records received

records accepted

records rejected

bytes received

unique records/day

corrections/day

duplicates/day

obscured/private percentage

poll duration

429 count

This data will determine future polling and retention.

==================================================
SOURCE CONTRACT DEBUG OUTPUT
==================================================

Provide authenticated developer/debug visibility for:

source contract version

last successful fetch

provider updated-as-of where available

records received/accepted/rejected

parser errors by sanitized code

rate-limit/backoff state

data freshness

proof roles

Do not expose secrets or sensitive coordinates.

==================================================
SHADOW ONLY
==================================================

M3 live sources initially feed:

raw observations
normalized assertions
M2 shadow patterns
debugging

They do NOT:

send notifications

create production Can't Miss

replace existing validated M1 opportunity output

Promoting live-source phenomena requires independent review.

==================================================
SOURCE CONTRACT TESTS
==================================================

Create contract fixtures from representative provider responses.

Fixtures must be sanitized but structurally faithful.

Test:

required identity

record updates

timestamp precision

geoprivacy

malformed record isolation

pagination

429/backoff

corrections

source freshness

schema drift / missing optional field

unknown enum values

No single record failure kills a page/batch.

==================================================
INATURALIST ACCEPTANCE TESTS
==================================================

At minimum:

I1
Open Research Grade observation.

Expected:
normalized presence with usable analysis geometry.

I2
Obscured observation.

Expected:
provider public point retained only as provider/raw obscured geometry;
not used as precise DBSCAN input.

I3
Private/no public coordinate.

Expected:
no invented geometry.

I4
Provider correction changes taxon.

Expected:
old normalized assertion superseded.

I5
Provider correction changes observed time.

Expected:
evidence freshness follows observation time.

I6
Provider changes open → obscured.

Expected:
protection increases; next M2 generation removes precise analysis point.

I7
Malformed one record among 200 valid.

Expected:
199/200 good records remain usable.

I8
Duplicate fetch same UUID.

Expected:
one provider record/current assertion.

I9
429.

Expected:
scheduler honors backoff.

I10
Date-only observation.

Expected:
date precision preserved; no invented exact timestamp.

I11
Description contains "feeding" or "cub".

Expected:
does NOT become confirmed canonical behavior merely from regex.

I12
Research Grade vs Needs ID.

Expected:
source quality retained and epistemic role differs according to policy.

==================================================
WFIGS ACCEPTANCE TESTS
==================================================

W1
Current wildfire perimeter intersects curated destination.

Expected:
shadow safety unsafe/hold candidate.

W2
Wildfire perimeter does not intersect destination.

Expected:
not automatically unsafe merely because same county/region.

W3
Prescribed fire.

Expected:
not silently treated as identical to wildfire.

W4
Historic/final old perimeter.

Expected:
does not act as current active safety block.

W5
Same IRWIN incident updates perimeter.

Expected:
provider correction updates current geometry, not duplicate independent fires.

W6
Malformed feature among valid features.

Expected:
valid features continue.

W7
Pagination / max-record-count handling.

Expected:
complete intended current result set.

==================================================
NWS CONTRACT TESTS
==================================================

N1
User-Agent configured.

N2
429/rate limitation.

N3
Alert update/correction.

N4
Stale underlying forecast/alert data despite HTTP success.

N5
Temperature is condition only, not Monarch confirmation.

==================================================
BLACK BEAR SHADOW TESTS
==================================================

B1
One credible iNaturalist bear record.

Expected:
signal only / no user spectacle.

B2
Multiple local independent records in provisional policy window.

Expected:
developing activity pattern.

B3
Three reports do not become "three bears."

B4
Description says "sow with cubs."

Expected:
text retained but no provider-confirmed sow/cub behavior in production semantics.

B5
Obscured bear record.

Expected:
regional corroboration only where policy permits; no tight centroid.

==================================================
MONARCH SHADOW TESTS
==================================================

M1
Single Monarch observation away from curated overwintering area.

Expected:
ordinary signal / hidden.

M2
Multiple relevant reports associated with curated overwintering grove/area.

Expected:
developing aggregation Watch candidate in shadow.

M3
Cool NWS morning.

Expected:
condition summary indicates clustered/resting photographic conditions may be
favored.

Does NOT create aggregation by itself.

M4
Warmer sunny condition.

Expected:
does not invalidate confirmed presence; may indicate more flying/basking
behavior.

M5
WFIGS active wildfire intersects public grove destination.

Expected:
safety hold candidate.

M6
No authoritative grove count exists.

Expected:
does not claim "major aggregation confirmed."

==================================================
NO BEHAVIOR REGEX CONFIRMATION
==================================================

Do not implement generic negative-lookbehind regex heuristics as a production
behavior engine in this slice.

If experimental parsing is useful:

store as:

derived_text_signal

with explicit provenance:

CORE_INFERENCE

not:

SOURCE_FACT

It cannot satisfy BEHAVIOR_CONFIRMATION.

==================================================
DATABASE
==================================================

Use existing generic source/observation structures wherever possible.

Do not create one custom observation table per provider.

Create a new migration only when necessary.

Do not edit migrations 0001–0006.

If needed:

0007

Keep schema source-neutral.

==================================================
SECRETS
==================================================

iNaturalist public read:
no secret required for first slice unless chosen endpoint proves otherwise.

WFIGS:
public ArcGIS read.

NWS:
User-Agent / contact configuration, not an API secret.

Do not commit credentials.

Future eBird token is NOT part of M3A.

==================================================
CI / LIVE-INTERNET TESTING
==================================================

Unit/contract tests must not depend on provider Internet availability.

Use recorded/sanitized fixtures.

A separate optional/manual live-contract verification command may call real
providers.

It must:

respect rate limits

make very few requests

never run uncontrollably in standard CI

report schema/contract drift clearly.

==================================================
IMPLEMENTATION REVIEW PACKET
==================================================

Create:

IMPLEMENTATION_REVIEW_MILESTONE_3A.md

Include:

1. Executive summary

2. Starting/final SHAs

3. M3 Source Contract design

4. L1 malformed-row correction

5. iNaturalist official API contract

6. iNaturalist identity

7. iNaturalist timestamp semantics

8. iNaturalist geoprivacy

9. iNaturalist count semantics

10. iNaturalist behavior boundaries

11. WFIGS contract

12. WFIGS wildfire vs prescribed/historic handling

13. NWS contract

14. Proof boundaries

15. Source roles

16. Polling/rate limits

17. Correction/update handling

18. Malformed-record isolation

19. Shadow integration

20. Black Bear shadow policy

21. Monarch shadow policy

22. Why temperature does not prove Monarch aggregation

23. Missing Monarch authoritative count source

24. Live volume measurements if performed

25. Tests and exact results

26. M1/M2 regression results

27. Privacy review

28. Known limitations

29. Deferred eBird contract issues

30. Deferred sources

31. Questions for Claude

==================================================
MANDATORY REGRESSION
==================================================

All M1/M2 accepted tests remain green.

Re-run:

M1 fixtures
pipeline parity
18,000 evaluator comparison

M2 A/F/P/B/C/H3 suites

privacy tests

identity tests

migration chain

Do not weaken M1/M2 to make a provider adapter pass.

==================================================
DO NOT IMPLEMENT
==================================================

No:

eBird
GBIF
BirdCast
USGS
CDEC
NWPS
CalHABMAP
CoastWatch
CDIP
MBARI
GOES
Sentinel
HPWREN
Caltrans
PurpleAir

in this first M3A slice.

No map.

No vision.

No public notifications.

No production promotion.

==================================================
FINAL STATUS
==================================================

At completion report separately:

M3A SOURCE-CONTRACT FOUNDATION = READY/NOT READY

INATURALIST LIVE ADAPTER = READY/NOT READY

WFIGS LIVE ADAPTER = READY/NOT READY

NWS CONTRACT = READY/NOT READY

BLACK BEAR SHADOW CALIBRATION = READY/NOT READY

MONARCH SHADOW CALIBRATION = READY/NOT READY

PRODUCTION PROMOTION = NO

==================================================
FINAL RESPONSE
==================================================

Return:

1. concise implementation summary

2. starting/final Core SHA

3. HA SHA and whether changed

4. migration if any

5. L1 result

6. Source Contract design

7. iNaturalist contract result

8. WFIGS contract result

9. NWS contract result

10. Black Bear shadow result

11. Monarch shadow result

12. provider contract test counts

13. full Core test count

14. M1/M2 regression results

15. optional live-contract verification results

16. CI status/links

17. review packet path

18. every known limitation

19. all deferred providers

20. explicitly:

M3A SOURCE-CONTRACT FOUNDATION = ...
INATURALIST LIVE ADAPTER = ...
WFIGS LIVE ADAPTER = ...
NWS CONTRACT = ...
BLACK BEAR SHADOW CALIBRATION = ...
MONARCH SHADOW CALIBRATION = ...
PRODUCTION PROMOTION = NO

End EXACTLY with:

READY FOR INDEPENDENT MILESTONE 3A REVIEW