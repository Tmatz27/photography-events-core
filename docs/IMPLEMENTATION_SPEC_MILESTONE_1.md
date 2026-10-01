You are the PRIMARY IMPLEMENTER for Photography Events Core, Milestone 1.

This is the beginning of a major architecture migration for an existing,
working Home Assistant project.

Read this entire prompt before changing anything.

Do not broaden the scope.
Do not add "helpful" future features.
Do not release anything.

At the end you MUST produce a detailed implementation review packet for an
independent Claude Code reviewer.

==================================================
PROJECTS / REPOSITORIES
==================================================

Existing Home Assistant repository:

https://github.com/Tmatz27/Home-assistant-photography-events

New Core repository to use/create:

https://github.com/Tmatz27/photography-events-core

If the Core repository does not yet exist:

- create it under the Tmatz27 GitHub account if your environment is authorized
  to do so
- initialize default branch as `main`
- do NOT create long-lived feature branches

If repository creation is not possible with available authorization:

- build the Core repository locally
- DO NOT create a differently named substitute repository
- clearly report that GitHub repository creation is the only blocked action
- provide the exact resulting local tree and commit
- do not silently put Core inside the HA repository

There are intentionally TWO repositories:

1. Home-assistant-photography-events

   Contains:
   - Home Assistant custom integration
   - config/options flow
   - Core client/bridge
   - HA entities
   - HA websocket interface for the card
   - Lovelace card
   - HACS packaging

2. photography-events-core

   Contains:
   - standalone Python Core application
   - REST API
   - database models
   - migrations
   - collectors/framework
   - normalization framework
   - intelligence framework
   - Dockerfile
   - Docker Compose
   - tests
   - documentation

The Lovelace card remains bundled with the Home Assistant integration.

The database is infrastructure belonging to the Core repository. It is NOT a
third repository.

==================================================
NORTH STAR
==================================================

Photography Events is a regret-prevention system for a nature photographer
based near Vandenberg SFB / Vandenberg Village, California.

The product asks:

"Is something happening, or about to happen, that is photographically
exceptional enough that I would regret not knowing about it?"

The system is NOT intended to be:

- a wildlife sighting feed
- an eBird clone
- an iNaturalist clone
- an encyclopedia
- a generic events calendar
- a tourism app

The operating philosophy is:

RESEARCH WIDELY
COLLECT BROADLY
ANALYZE AGGRESSIVELY
DISPLAY VERY NARROWLY

Conceptual funnel:

SIGNAL
→
PATTERN
→
PHENOMENON
→
OPPORTUNITY

A report is evidence.
A season is context.
A sighting is a signal.
A photographic phenomenon is an event.

==================================================
CURRENT PRODUCTION BASELINE
==================================================

The existing Home Assistant v0.16.x family is the production baseline.

It has undergone substantial testing and adversarial review.

DO NOT rewrite it.

DO NOT break it.

DO NOT switch users to Core by default.

Before editing the HA repository:

git pull --ff-only

Record:

- current main SHA
- current VERSION
- manifest version
- current test counts
- relevant current architecture

The existing local engine remains authoritative during Milestone 1.

==================================================
TARGET ARCHITECTURE
==================================================

Eventually:

External Data Sources
        ↓
Photography Events Core
Docker on Unraid
        ↓
PostgreSQL + PostGIS
        ↓
Core REST API
        ↓
Home Assistant Integration
        ↓
HA entities + Lovelace card

The browser/card must NEVER talk directly to Core.

The intended UI path is:

Lovelace Card
        ↓
Home Assistant websocket/custom command
        ↓
Photography Events HA integration
        ↓
Photography Events Core REST API

Home Assistant becomes:

- presentation
- automation
- notification
- secure bridge/client

Core becomes:

- collection
- storage
- normalization
- intelligence
- source health
- opportunity generation
- historical state

==================================================
MILESTONE 1 SCOPE
==================================================

Milestone 1 is FOUNDATION + PARITY VERTICAL SLICE.

It is NOT the full 0.17 migration.

Implement:

1. New Core repository/application
2. PostGIS database
3. Explicit schema migrations
4. Core configuration
5. Structured logging
6. REST API foundation
7. authentication
8. liveness/readiness
9. phenomenon-definition framework
10. deterministic parity fixtures/harness
11. Carrizo Plain Tule Elk Rut vertical slice
12. Pinnacles Condor vertical slice if it can be added cleanly after Tule Elk
13. Core client scaffolding in HA
14. HA/Core asynchronous connectivity and failure handling
15. Docker Compose for Unraid
16. backup/restore documentation and verification
17. complete automated tests
18. comprehensive implementation review packet

DO NOT implement yet:

- generalized DBSCAN clustering
- raw signal aggregation UI
- BirdCast
- USGS OGC
- CDEC
- NWPS
- CalHABMAP
- CoastWatch
- Sentinel-2
- GOES
- HPWREN
- MBARI
- new phenomena
- Map UI
- Intel iGPU/OpenVINO worker
- machine-learning models
- Redis
- Celery
- Kafka
- RabbitMQ
- Elasticsearch
- TimescaleDB

The architecture must allow these later without implementing them now.

==================================================
FIRST PARITY PHENOMENON
==================================================

Use the EXISTING:

Carrizo Plain Tule Elk Rut

from the current Home Assistant implementation.

Do NOT use Point Reyes.

Do NOT invent a new Tule Elk location.

Capture the current real implementation semantics before porting it.

The purpose of this vertical slice is to exercise:

- curated phenomenon
- season/window
- location
- evidence
- presentation
- eligibility
- drive treatment
- gear/advice serialization where applicable
- opportunity identity
- API serialization

Second vertical slice, if cleanly achievable after the first:

existing Pinnacles Condor opportunity

This introduces observation-backed evidence without implementing generalized
observation clustering.

==================================================
DATABASE
==================================================

Use one dedicated PostGIS container.

Image:

postgis/postgis:18-3.6

This container provides BOTH:

PostgreSQL 18
PostGIS 3.6

Do NOT create a separate plain PostgreSQL container.

Database:

photography_events

Application database user:

photography_events

Photography Events must NOT reuse:

- Immich PostgreSQL
- AdventureLog PostGIS
- existing MariaDB
- any other application's database

==================================================
UNRAID STORAGE
==================================================

Default documented production paths:

Database:

/mnt/cache/appdata/photography-events-db/

Core:

/mnt/cache/appdata/photography-events-core/

Do not use `/mnt/user` as the recommended active PostgreSQL storage path.

Make host paths configurable through environment variables or Compose `.env`
where practical rather than hard-coding them throughout the application.

PostgreSQL 18 image data-volume semantics must be handled correctly.

The PostGIS/PostgreSQL container must NOT expose port 5432 to the LAN by
default.

Core and PostgreSQL communicate over a private Compose network.

Core exposes only the LAN API port necessary for Home Assistant.

==================================================
DOCKER SERVICES
==================================================

Initial production topology:

photography-events-core
photography-events-db

Only.

Do not add infrastructure services.

Compose must include:

- explicit service names
- private DB network
- persistent storage
- environment file support
- health checks
- restart behavior
- dependency/readiness handling
- no hard-coded secrets
- predictable container names if appropriate for Unraid
- documentation for Unraid Compose installation

==================================================
PRIMARY KEY STRATEGY
==================================================

For high-volume internal tables prefer:

BIGINT GENERATED BY DEFAULT AS IDENTITY

or equivalent modern PostgreSQL identity semantics.

Do NOT use legacy SERIAL/BIGSERIAL merely because Gemini suggested BIGSERIAL.

UUIDs are not prohibited, but do not use random UUIDv4 everywhere by default.

Stable PRODUCT identities remain deterministic textual keys where appropriate:

- source key
- phenomenon key
- occurrence_key

Database row IDs and product identity are separate concepts.

==================================================
PHENOMENON DEFINITIONS
==================================================

Executable phenomenon logic must remain version controlled in the Core Git
repository.

Do NOT store executable trigger/evidence/cluster/decay policies as arbitrary
JSONB in PostgreSQL.

Use versioned Python/YAML or an equally inspectable source-controlled format.

The database should retain enough provenance to know which rules created a
historical decision.

At minimum opportunities/revisions should be capable of recording:

definition_key
definition_version
definition_hash
engine_version

The objective:

Git controls the rules.

PostgreSQL records which rule version produced a decision.

==================================================
DATABASE SCHEMA - AUTHORITATIVE DIRECTION
==================================================

Implement only what Milestone 1 needs, but design migrations so the following
model is supported.

Do not create empty speculative tables merely to satisfy a checklist when they
are not yet required.

However, do not make schema decisions that prevent this model later.

--------------------------------------------------
sources
--------------------------------------------------

Provider definition/state.

Conceptually:

id BIGINT identity PK
key TEXT UNIQUE NOT NULL
name TEXT NOT NULL
source_type TEXT
base_url TEXT
enabled BOOLEAN NOT NULL DEFAULT TRUE
poll_interval_sec INTEGER
timeout_sec INTEGER

created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ

Executable rate-limit/freshness policy belongs primarily in code/config, not
opaque database JSONB.

Source-specific operational state that must survive restart may be persisted.

--------------------------------------------------
source_roles
--------------------------------------------------

Relational mapping for epistemic roles.

source_id FK
role

Allowed roles:

DISCOVERY
PLANNING
WATCH_SIGNAL
CONFIRMATION
CORROBORATION
CONDITION
ACCESS
SAFETY

Use constraints/enums/checks appropriately.

Do not use an uncontrolled TEXT[] for these roles.

--------------------------------------------------
collection_cycles / source_runs
--------------------------------------------------

Collection history must be APPEND-ONLY enough to preserve actual failures and
retries.

Do NOT overwrite a failed run with retry success.

It is acceptable to model:

collection_cycle
    ↓
multiple source_run attempts

or another clean equivalent.

Store enough to answer:

- when was a request attempted?
- what happened?
- how long did it take?
- was it a retry?
- what provider timestamp was returned?
- how many records were accepted/rejected?

Conceptual source_run fields:

id
source_id
collection_cycle_id nullable
attempt_number
started_at
completed_at
status
http_status
records_received
records_accepted
records_rejected
provider_updated_at
latency_ms
error_code
error_message
metadata if genuinely useful

Do NOT erase failure history.

--------------------------------------------------
source health
--------------------------------------------------

Prefer a VIEW/current-state projection derived from source runs and freshness
rules rather than another independently mutable truth table.

If some small persisted operational state is needed for backoff, keep it
separate from semantic source health.

Initial user-facing source states:

UP
STALE
DOWN

Do not invent probabilistic uptime scoring.

--------------------------------------------------
raw_observations
--------------------------------------------------

Provider-native evidence.

Conceptually:

id BIGINT identity PK

source_id FK

source_run_id FK nullable

external_id TEXT nullable

subject_raw TEXT nullable

observed_at TIMESTAMPTZ nullable
published_at TIMESTAMPTZ nullable
fetched_at TIMESTAMPTZ NOT NULL

exact_geometry GEOMETRY(Point, 4326) nullable

location_precision_m DOUBLE PRECISION nullable

raw_count INTEGER nullable

raw_behavior TEXT nullable

raw_payload JSONB

parser_version TEXT

created_at TIMESTAMPTZ

Do NOT add per-row `expires_at` solely to manage raw-data retention.

Retention is an application/storage policy.

Critical principle:

FETCH TIME != OBSERVATION TIME

`fetched_at` must never renew stale evidence.

For providers with stable external IDs:

UNIQUE(source_id, external_id)

must be supported.

For providers without stable IDs:

do NOT pretend a weak hash proves semantic identity.

Design a documented deterministic deduplication/fingerprint mechanism that can
be source-specific.

Raw payload is an appropriate use of JSONB.

--------------------------------------------------
normalized_observations
--------------------------------------------------

Provider-independent assertions.

A SINGLE RAW RECORD MAY PRODUCE MULTIPLE NORMALIZED OBSERVATIONS.

Therefore:

DO NOT make raw_observation_id UNIQUE.

Conceptually:

id BIGINT identity PK

raw_observation_id FK

subject_type
subject_key
taxon_id nullable

observed_at

analysis_geometry GEOMETRY(Point,4326) nullable

public_geometry GEOMETRY(Point,4326) nullable

location_precision_m

reported_count nullable

valid_until nullable

sensitive BOOLEAN

precision_class

created_at
updated_at

Behavior representation should be structured enough for future querying.

Do not blindly create free-form arrays if a relational model is clearly
superior.

==================================================
SPATIAL GEOMETRY PRINCIPLE
==================================================

Conceptually distinguish:

EXACT GEOMETRY
what a provider supplied

ANALYSIS GEOMETRY
what Core is allowed to use for intelligence

PUBLIC GEOMETRY
what is safe to expose outside Core

These need not all be physically duplicated when unnecessary, but the security
boundary must exist.

Exact sensitive coordinates should remain restricted to raw ingestion data.

Sensitive location protection must NOT be a universal:

round to 3 decimals

rule.

Depending on species/location policy, public geometry may be:

- exact known-safe public location
- generalized region
- curated public viewing site
- heavily fuzzed point
- NULL

For sensitive wildlife:

nest/den/private/sensitive precise coordinates must never leave Core.

==================================================
GEOMETRY / POSTGIS
==================================================

Use:

GEOMETRY(..., 4326)

as the canonical stored spatial representation unless a specific table requires
a clearly justified alternative.

Apply GiST indexes where spatial access patterns require them.

Future distance/clustering calculations in meters must NOT run DBSCAN directly
against longitude/latitude degree units.

For clustering/distance operations that require metric distances:

transform to an appropriate projected CRS or otherwise use a spatial operation
with correct units.

Do not implement homemade degrees-to-miles approximations.

Generalized clustering is NOT Milestone 1.

==================================================
locations
==================================================

Curated locations must eventually support more than points.

A location may represent:

- public viewpoint
- trailhead
- park
- refuge
- bay
- region
- migration zone

Do not design the schema so every location must forever be a Point.

Support geometry capable of future Point/Polygon/MultiPolygon use, or provide
a clear location-geometry model.

Conceptual metadata:

id
key UNIQUE
name
region
geometry
public_geometry
location_type
sensitivity
timezone
created_at
updated_at

Avoid burying important queryable facts in arbitrary `access_metadata` JSONB.

==================================================
phenomenon locations
==================================================

Maintain many-to-many relationship between phenomenon definition keys and
locations where necessary.

Phenomenon rules remain version controlled.

A relationship may eventually need:

role
priority
seasonality
viewpoint/public-viewing role

Do not overbuild this in Milestone 1.

==================================================
observation clusters - FUTURE PHASE
==================================================

Do NOT implement generalized clustering now.

But when later implemented, it MUST include explicit provenance.

Future tables:

observation_clusters
cluster_members

cluster_members:

cluster_id FK
normalized_observation_id FK

A cluster without its membership is unacceptable.

Future cluster information may include:

subject
time window
centroid
radius
observation count
independent report/source count
behavior summary
valid_until

Do NOT initially persist misleading polygon footprints simply because they can
be computed.

Cluster `12 observations` must NEVER be presented as `12 animals` unless actual
count evidence supports that.

==================================================
EVIDENCE MODEL
==================================================

Do NOT implement a polymorphic foreign-key anti-pattern such as one evidence
row containing:

raw_observation_id
normalized_observation_id
cluster_id

with two usually NULL.

Use strict relational association tables appropriate to the evidence type.

Future examples might include:

opportunity_observation_evidence
opportunity_cluster_evidence
opportunity_context_evidence

Exact naming is flexible.

The point is:

referential integrity must be enforceable by PostgreSQL.

Evidence disposition should support:

SUPPORTING
CONTRADICTORY
NEUTRAL

Negative evidence matters.

Example:

"Webcam confirms no fog"

may legitimately demote a developing fog opportunity.

Preserve provenance.

==================================================
OPPORTUNITIES
==================================================

The core product entity.

Conceptually:

id BIGINT identity PK

phenomenon_key
location_id nullable

occurrence_key TEXT UNIQUE NOT NULL

starts_at
ends_at

presentation

eligibility

significance

confidence

urgency

evidence_state

access_state

safety_state

condition_state

drive_minutes nullable

drive_basis nullable

reason

awaiting

definition_version
definition_hash
engine_version

created_at
updated_at

Keep:

PRESENTATION

separate from:

ELIGIBILITY

Presentation may include:

cant_miss
watching
planner
held

Eligibility expresses whether required gates are actually satisfied.

Do not merge these concepts.

==================================================
OCCURRENCE IDENTITY
==================================================

Stable occurrence identity is critical.

Follow/Skip/Seen/announcement state must not randomly reset after recalculation
or migration.

Do NOT use a random database ID as product occurrence identity.

Preserve/reproduce existing deterministic occurrence semantics wherever
possible.

If the current v0.16 implementation uses a particular occurrence algorithm,
understand it before porting it.

Do not replace it casually with:

hash(phenomenon, location, year)

unless that is proven semantically equivalent.

==================================================
OPPORTUNITY HISTORY
==================================================

Do NOT reduce history to only:

WATCHING → CAN'T MISS

We want meaningful decision history even when presentation remains unchanged.

Implement or prepare for:

opportunity_revisions

Append a revision when MATERIAL decision state changes, for example:

- presentation
- eligibility
- significance
- confidence beyond meaningful threshold
- urgency
- evidence state
- access
- safety
- condition
- definition version
- decision reason

Do NOT snapshot a giant arbitrary JSON object every polling interval.

Do NOT create a new revision when nothing meaningful changed.

Historical revisions should allow future analysis of:

- when we first detected an event
- how confidence changed
- when it became Can't Miss
- whether we gave enough advance warning
- which engine/definition produced the decision

==================================================
ROUTE BASELINES
==================================================

For fixed curated destinations:

calculate routed baseline once
persist
reuse

Conceptually:

origin_key
location_id
routing_profile
distance_miles
drive_minutes
provider
calculated_at
invalidated_at

Unique:

(origin_key, location_id, routing_profile)

Keep distinct:

DISTANCE
How far is this normally?

ACCESS
Can I physically/legal reach it today?

SAFETY
Should I go?

CONDITIONS
Will the photograph likely be worthwhile?

A road closure changes ACCESS.

A road closure does NOT overwrite the normal baseline drive-time concept.

Dynamic sightings should not trigger road-routing while they are merely raw
signals.

==================================================
ENVIRONMENTAL DATA
==================================================

Do NOT implement one generic:

environmental_context(type, values JSONB)

table as the permanent answer.

Do NOT prematurely create every possible future environmental table either.

Milestone 1 only needs the minimum strongly typed structures necessary to
achieve parity for its vertical slices.

When future source families are implemented, add domain-appropriate strongly
typed data models such as:

weather observations/forecasts
safety alerts
marine conditions
hydrology
vegetation

where real query requirements justify them.

==================================================
PARTITIONING
==================================================

DO NOT partition raw_observations or source_runs in Milestone 1.

Expected scale does not currently justify partition-management complexity.

Instead:

- appropriate indexes
- retention sweeper
- batch cleanup
- PostgreSQL autovacuum
- actual volume measurements

Design migrations so native partitioning can be added later if retention DELETE
cost or table size proves it necessary.

Do not implement infrastructure because a hypothetical future workload might
need it.

==================================================
INDEXING
==================================================

Add indexes according to actual query patterns.

At minimum examine:

GiST:

spatial geometry columns that will be queried spatially

B-tree:

observed_at
valid_until
source_id
phenomenon/location identifiers
presentation

Compound/partial indexes where justified for active opportunities.

Remember:

PostgreSQL does not automatically create indexes on referencing FK columns.

Add FK-supporting indexes where delete/join behavior requires them.

Do not mechanically index every column.

Document every non-trivial index and the query pattern it serves.

==================================================
TEMPORAL VALIDITY
==================================================

Temporal validity is first-class.

Milestone 1 may use explicit:

valid_until

for evidence assertions where needed.

Executable decay behavior belongs in versioned code/config.

Do NOT implement continuous mathematical decay curves in SQL in Milestone 1.

Future source/phenomenon rules may have different lifetimes.

A stale source/evidence must never support Can't Miss forever.

==================================================
SOURCE RATE-LIMIT / BACKOFF FRAMEWORK
==================================================

Provide a framework for future collectors.

Shared scheduling/network infrastructure must support:

- minimum poll interval
- request timeout
- HTTP 429
- Retry-After
- exponential backoff
- jitter
- consecutive failures
- source-specific policy

Operational state needed to survive Core restart should be persistable.

Do not implement fifteen collectors simply to exercise this framework.

No source loop may hammer providers on repeated failure.

==================================================
RETENTION / SWEEPER
==================================================

Provide application-level retention machinery/framework.

Do not confuse application retention with PostgreSQL VACUUM.

PostgreSQL autovacuum handles dead tuples.

Application sweeper handles business retention.

Initial guidance:

raw provider payload:
approximately 30–90 days depending on source

normalized observations:
longer, policy dependent

clusters:
long-term where useful

opportunity revisions:
long-term

source runs:
finite operational history

Do not permanently retain bulk:

satellite images
radar images
webcam frames

in future unless specifically justified.

==================================================
CORE API
==================================================

Use FastAPI unless inspection reveals a compelling reason otherwise.

API v1 should be intentionally small.

Required:

GET /health/live

GET /health/ready

GET /api/v1/opportunities

GET /api/v1/opportunities/{occurrence_key}

GET /api/v1/sources/health

Health responses should expose version information sufficiently that a separate
/version endpoint is not required unless you can clearly justify it.

==================================================
HEALTH SEMANTICS
==================================================

/health/live

Answers:

"Is the Core process alive?"

Should not fail merely because a downstream provider is stale.

/health/ready

Answers:

"Can Core currently serve valid application requests?"

PostgreSQL unavailable should make readiness fail.

Appropriate HTTP statuses:

live healthy:
200

ready healthy/degraded-but-servable:
document behavior carefully

not ready:
503

Never convert DB failure into empty opportunity results.

==================================================
OPPORTUNITIES API
==================================================

Use a consolidated resource instead of duplicating backend logic.

Examples:

GET /api/v1/opportunities?presentation=cant_miss

GET /api/v1/opportunities?presentation=watching

GET /api/v1/opportunities?presentation=planner

GET /api/v1/opportunities?category=birds

The HA card may still visibly present:

CAN'T MISS
WATCHING
YEAR PLANNER
BIRDS

The REST implementation should not need four duplicate endpoints merely because
the UI has four tabs.

Support only filtering needed for Milestone 1 but define schemas with future
compatibility in mind.

==================================================
API RESPONSE ENVELOPE
==================================================

Opportunity-list responses must distinguish:

COMPLETE + EMPTY

from:

INCOMPLETE/DEGRADED ASSESSMENT

A source failure must never make:

items: []

mean:

"Nothing worth changing plans for."

Response schema should include meaningful fields such as:

generated_at
data_as_of
assessment_state
missing_required_sources
degraded_sources
items

Exact final naming can be refined.

Assessment semantics must be explicit and tested.

==================================================
API ERRORS
==================================================

Use a consistent error structure.

Conceptually:

{
  "error": {
    "code": "...",
    "message": "..."
  }
}

Do not leak:

- secrets
- database connection strings
- stack traces
- API tokens

through normal API errors.

==================================================
API SCHEMAS
==================================================

Use strongly typed Pydantic/OpenAPI schemas.

Do not return arbitrary database ORM objects.

The API is a contract between two independently versioned repositories.

Design fields so additive compatible changes can occur without breaking the HA
integration.

==================================================
API VERSIONING
==================================================

Core software version and HA integration version are independent.

Example:

Core software:
0.1.x

HA integration:
0.17.x

API:
v1

They do NOT need matching software versions.

Core health/API metadata should expose:

core_version
api_version
schema_version

HA validates API compatibility, not matching package versions.

==================================================
AUTHENTICATION
==================================================

Core is LAN infrastructure.

Initial authentication:

one generated bearer token

HA stores:

Core URL
API token

Requests:

Authorization: Bearer <token>

The Core secret should come from:

environment variable
or Docker secret

Do NOT put authentication dependency in PostgreSQL for Milestone 1.

If the DB is down, authentication should not suddenly become impossible to
evaluate health behavior.

Do NOT expose the token to the Lovelace card.

Do NOT build:

OAuth
user accounts
RBAC
Internet login

for this LAN appliance use case.

==================================================
HOME ASSISTANT NETWORKING
==================================================

ALL Core communication from Home Assistant must be asynchronous.

Use:

Home Assistant async HTTP helpers
or aiohttp

Never:

requests.get()
blocking sockets
sync HTTP inside the HA event loop

Timeouts are mandatory.

Core unavailability must NEVER hang Home Assistant.

==================================================
HA CORE CLIENT
==================================================

Add an isolated client abstraction.

Conceptually:

PhotographyEventsCoreClient

Responsibilities:

- authentication
- timeout
- API version validation
- typed response parsing
- error translation
- health/readiness query
- opportunity query

Do not spread raw aiohttp calls throughout the integration.

==================================================
HA BACKEND MODE
==================================================

DO NOT switch production behavior to Core by default in Milestone 1.

Existing local/legacy engine remains functional.

It is acceptable to introduce an advanced/developer Core connection mode or
scaffolding for testing.

Do not remove the local engine.

Do not require Core for normal v0.16.x operation yet.

Document exactly how Core mode/testing is activated.

==================================================
HA CARD / CACHE FAILURE BEHAVIOR
==================================================

Future production behavior must support:

Core online:
show current data

Core offline:
show cached data clearly marked STALE, where safe

But memory-only cache is insufficient.

If Home Assistant restarts while Core is offline, useful last-known product
state should not necessarily disappear.

Design a lightweight cache strategy:

- in-memory hot cache
- persisted last-known successful rich payload + timestamp using appropriate HA
  storage mechanism

Do not persist huge provider payloads in HA.

Cache product/API results only.

Different content may ultimately require different freshness limits.

For example:

Can't Miss data should age out faster than year-planner context.

Milestone 1 should implement only the cache behavior necessary for the vertical
slice/bridge while documenting future TTL policy.

When Core is unavailable:

HA must not say:

"Nothing worth changing plans for."

==================================================
CORE DATABASE FAILURE
==================================================

When Postgres is unavailable:

/health/live may still be alive

/health/ready should fail

data routes should return 503

Core must not synthesize:

[]

HA must remain responsive.

Tests must explicitly cover this.

==================================================
ALEMBIC / MIGRATIONS
==================================================

Use Alembic or a clearly superior equivalent.

Alembic is preferred.

Spatial migrations must be reviewed/written explicitly.

Do NOT blindly trust Alembic autogenerate to correctly mutate:

PostGIS types
GiST indexes
extensions

Autogenerate may assist ordinary schema changes, but migration files must be
human-readable and deliberately reviewed.

Initial migration must explicitly enable/verify PostGIS extension requirements.

==================================================
PARITY HARNESS
==================================================

This is NON-NEGOTIABLE.

Independent tests passing in both projects are NOT parity.

Capture deterministic fixtures from the existing Home Assistant engine.

For identical logical inputs:

LEGACY ENGINE
vs
CORE ENGINE

must be semantically compared.

Compare at least where applicable:

phenomenon identity
occurrence identity
dates/windows
eligibility
presentation
significance
confidence
urgency
drive treatment
safety
access
evidence state
reason/awaiting semantics
Can't Miss membership
Watching classification
Bird classification where relevant

Structural JSON equality is not required because architectures differ.

Semantic equality IS required.

Build a normalization layer for parity comparisons where serialization differs.

==================================================
KNOWN BUGS DURING PARITY
==================================================

Do not opportunistically "fix" unrelated old logic during the initial parity
port.

If a known legacy behavior is clearly wrong:

- document it
- preserve parity for Phase B if safe
- identify it for a later intentional behavior-change phase

If preserving a legacy behavior would be unsafe or materially incorrect:

STOP and report it rather than silently diverging.

The goal is to know whether differences come from migration or intentional
product changes.

==================================================
TULE ELK FIXTURE
==================================================

Inspect the actual existing:

Carrizo Plain Tule Elk Rut

implementation.

Capture a deterministic fixture.

Port only enough existing logic into Core to reproduce its meaningful
opportunity result.

Do not fake parity by hard-coding the final expected JSON.

The Core must evaluate the fixture through the new phenomenon/application
layer.

==================================================
PINNACLES CONDOR FIXTURE
==================================================

After Tule Elk parity passes:

add the existing Pinnacles Condor opportunity as a second vertical slice if
doing so does not expand Milestone 1 uncontrollably.

This should test more evidence-backed behavior and safe/public location
treatment.

Do NOT implement generalized clustering to make this work.

If Condor requires too much unrelated migration, defer it and clearly document
why.

Tule Elk parity is mandatory.

Condor parity is strongly preferred but may be deferred with evidence.

==================================================
NO NEW LIVE DATA SOURCES
==================================================

Do NOT add:

BirdCast
USGS
CDEC
CalHABMAP
CoastWatch
Sentinel
GOES
HPWREN
MBARI

during Milestone 1.

Existing provider fixtures may be used for parity.

Do not contaminate migration testing with new intelligence.

==================================================
BACKUP
==================================================

Document and test:

pg_dump -Fc

custom-format backup.

Destination production intent:

nightly to existing Synology NAS

Do not build a complicated backup orchestration service.

Provide:

backup command/script
restore command/script
required environment variables
documentation

==================================================
RESTORE ACCEPTANCE
==================================================

A backup is not considered implemented until restore is demonstrated.

Test process:

1. create backup
2. create clean/empty compatible PostGIS database
3. ensure required extension state
4. restore with pg_restore
5. run/verify migrations/schema version
6. start Core
7. readiness passes
8. vertical-slice data is readable

Document exact result.

==================================================
STRUCTURED LOGGING
==================================================

Core logs must clearly distinguish:

- startup
- migration/schema issue
- database unavailable
- database recovered
- source collection failure
- source stale
- parser failure
- scheduler failure
- API request failure
- authentication failure
- parity test failure

Do not log secrets.

==================================================
SCHEDULER
==================================================

Milestone 1 only needs a minimal scheduler architecture.

Do not introduce Redis-backed workers.

Use asyncio / APScheduler / another lightweight approach if justified.

Document why chosen.

It must support graceful shutdown and avoid overlapping duplicate source jobs.

Future rate-limit/backoff state must be able to survive restart where
necessary.

==================================================
FUTURE iGPU
==================================================

The Unraid host has an unused Intel UHD 770 iGPU.

DO NOT use it during Milestone 1.

Do NOT map /dev/dri into Core.

Future:

photography-events-vision

may become a separate optional container using OpenVINO.

Core must never depend on the GPU worker.

==================================================
SECURITY
==================================================

Core:

LAN only

No:
Cloudflare exposure
Internet listener
router port-forward
public API

Postgres:

private Compose network only

Secrets:

not committed

Provide:

.env.example

containing names/placeholders only.

`.env` must be gitignored.

Do not print secrets during startup.

==================================================
TESTING
==================================================

Add comprehensive automated tests appropriate to Milestone 1.

Core tests should include at minimum:

- configuration
- authentication
- liveness
- readiness
- DB healthy
- DB unavailable
- migrations
- PostGIS extension
- model constraints
- external ID uniqueness where applicable
- one raw → many normalized relationship
- stable occurrence identity
- opportunity serialization
- API filtering
- complete-empty vs incomplete/degraded assessment
- source health projection
- route baseline uniqueness
- backup command sanity where testable
- Tule Elk parity

HA tests should include where applicable:

- async Core client
- timeout
- authentication failure
- unsupported API version
- Core unavailable
- DB/Core readiness failure
- HA does not block
- legacy mode still works
- persisted Core cache behavior implemented in this milestone
- existing integration tests remain passing

Run existing HA tests as well.

==================================================
LINT / STATIC VALIDATION
==================================================

Use the project's existing tooling where applicable.

Core should have a minimal, maintainable Python quality toolchain.

Do not introduce five overlapping linters.

At minimum validate:

- syntax
- typing where adopted
- tests
- Docker/Compose validity
- migration consistency
- OpenAPI generation

==================================================
DEPENDENCIES
==================================================

Use stable, justified dependencies.

Do not add libraries solely for minor conveniences.

Document major choices such as:

FastAPI
SQLAlchemy
GeoAlchemy2 if used
Alembic
Pydantic
httpx/aiohttp
scheduler library

Pin dependencies appropriately for reproducible Docker builds.

==================================================
README / DOCUMENTATION
==================================================

Core README must cover:

Purpose

Architecture

Requirements

Docker Compose installation

Unraid paths

Environment variables

Database initialization

How migrations run

Health checks

Authentication

Backup

Restore

Development startup

Tests

Parity harness

Relationship to Home Assistant repository

Milestone 1 limitations

What is intentionally deferred

==================================================
HA REPOSITORY DOCUMENTATION
==================================================

Do not rewrite the entire HA README unless necessary.

Document only new developer/Core behavior introduced in Milestone 1.

Do not advertise Core as a required production dependency yet.

==================================================
RELEASES
==================================================

DO NOT:

tag
publish
create GitHub Release
publish HACS update
bump existing HA release to public 0.17
remove 0.16 behavior

The new Core may identify itself internally as an initial development version
such as 0.1.0-dev if needed.

This is not a public release.

==================================================
GIT WORKFLOW
==================================================

Main-only workflow.

For each repository:

git pull --ff-only before edits where remote exists

Do not force push.

Do not create a collection of long-lived branches.

Make logically clean commits.

Do not mix accidental unrelated formatting changes.

Push normally after intended validation succeeds.

If CI fails:

investigate it.

Do not report "ready" while CI is red.

==================================================
MILESTONE 1 ACCEPTANCE CRITERIA
==================================================

Milestone 1 is not complete until all applicable items below are demonstrated.

CORE:

[ ] Core container builds

[ ] PostGIS container starts

[ ] persistent DB storage works

[ ] PostGIS extension works

[ ] Alembic migrations work from empty DB

[ ] migrations are repeat-safe/idempotent as appropriate

[ ] Core starts against migrated DB

[ ] /health/live works

[ ] /health/ready works

[ ] bearer authentication works

[ ] opportunities API works

[ ] source health API works

[ ] Tule Elk parity passes

[ ] stable occurrence identity demonstrated

[ ] Core restart preserves DB data

[ ] DB restart recovery demonstrated

[ ] DB unavailable produces not-ready / 503 rather than empty data

[ ] pg_dump -Fc succeeds

[ ] restore into clean DB succeeds

[ ] restored Core becomes ready

HOME ASSISTANT:

[ ] existing local engine still works

[ ] existing card/integration tests still pass

[ ] Core client uses async networking only

[ ] Core failure cannot block HA

[ ] API version incompatibility is handled

[ ] no Core token reaches the browser/card

[ ] Core is NOT required by default

SECURITY/OPS:

[ ] DB port not published by default

[ ] secrets not committed

[ ] .env.example safe

[ ] Unraid cache path documented

[ ] logs do not expose secrets

SCOPE:

[ ] no DBSCAN implementation

[ ] no Map

[ ] no iGPU worker

[ ] no new live source families

[ ] no public v0.17 release

==================================================
MANDATORY IMPLEMENTATION REVIEW PACKET
==================================================

At the end create:

IMPLEMENTATION_REVIEW_MILESTONE_1.md

Prefer placing it in the Core repo.

If cross-repo details require supporting docs, link them from this master
packet.

This packet is REQUIRED because another coding model will independently review
your implementation.

It must contain:

# 1. EXECUTIVE SUMMARY

What was actually accomplished.

# 2. REPOSITORIES

For EACH repository:

- URL
- original main SHA
- final main SHA
- commits created

# 3. ARCHITECTURE IMPLEMENTED

Actual architecture, not planned architecture.

Include a diagram.

# 4. PROMPT DEVIATIONS

For every meaningful deviation from this specification:

- requested behavior
- implemented behavior
- why
- risk

Do not hide deviations.

# 5. FILE INVENTORY

Every significant file:

created
modified
deleted

and why.

# 6. CORE DEPENDENCIES

List major packages and versions.

Explain each non-obvious dependency.

# 7. DOCKER DESIGN

Document:

services
images
ports
networks
volumes
healthchecks
restart policies
dependency behavior

# 8. UNRAID DEPLOYMENT

Exact host paths.

Exact startup steps.

Exact `.env` fields.

# 9. DATABASE SCHEMA

Every Milestone-1 table/view.

Include:

columns
types
PKs
FKs
unique constraints
check constraints
indexes

# 10. POSTGIS

Document:

extension version
spatial types used
GiST indexes
spatial functions used
CRS assumptions

# 11. MIGRATIONS

Migration list/order.

Explain any manually written spatial migration behavior.

# 12. PHENOMENON DEFINITIONS

Explain how rules are source-controlled.

Document:

definition key
version
hash behavior

# 13. TULE ELK PORT

Explain exactly which existing implementation was used.

Document mapping:

legacy logic
→
Core logic

# 14. CONDOR PORT

If implemented:

same detail.

If deferred:

exact reason.

# 15. PARITY HARNESS

Describe:

fixture origin
fixture freezing
normalization
semantic equality rules
known allowed differences

# 16. PARITY RESULTS

Exact results.

Do not write merely "passes."

Show what fields were compared.

# 17. CORE API

Every endpoint.

Request/query parameters.

Response schema.

Authentication.

Status/error semantics.

# 18. HEALTH / READINESS

Explain exactly what each endpoint tests.

# 19. AUTHENTICATION

Secret source.

Comparison method.

How HA stores it.

How token exposure is prevented.

# 20. HA INTEGRATION CHANGES

Every change.

Explicit confirmation that existing local mode still works.

# 21. ASYNC SAFETY

Demonstrate that no blocking Core HTTP calls were introduced to HA.

# 22. CACHE / OFFLINE BEHAVIOR

What is implemented now.

What remains deferred.

# 23. SOURCE HEALTH

How current state is derived.

# 24. RATE-LIMIT FRAMEWORK

What exists now.

What remains future.

# 25. RETENTION

Current implemented retention behavior.

Future plan.

# 26. BACKUP

Exact command used.

Backup size/result.

# 27. RESTORE

Exact test performed.

Result.

# 28. TESTS

For each repository:

exact test commands

exact test count

passes/failures/skips

# 29. STATIC / LINT / BUILD VALIDATION

Exact commands/results.

# 30. DOCKER VALIDATION

Build result.

Startup result.

Health result.

Restart result.

# 31. FAILURE INJECTION

Document tests/results for:

DB stopped
DB restarted
Core restarted
bad token
Core unreachable from HA
unsupported API version

# 32. SECURITY REVIEW

Ports.

Networks.

Secrets.

Sensitive geometry handling.

Known concerns.

# 33. PERFORMANCE REVIEW

Expected load.

Indexes.

DB connection pooling.

Anything potentially blocking.

# 34. KNOWN LIMITATIONS

Be explicit.

# 35. DEFERRED FEATURES

Confirm each major future feature that was intentionally NOT implemented.

# 36. TECHNICAL DEBT CREATED

Anything deliberately temporary.

# 37. QUESTIONS FOR INDEPENDENT REVIEWER

List anything you believe deserves adversarial scrutiny.

# 38. NEXT MILESTONE RECOMMENDATION

Do not implement it.

Describe what should logically come next.

==================================================
INDEPENDENT REVIEW PREPARATION
==================================================

Assume Claude Code will receive:

- both repository SHAs
- this review packet
- this original implementation specification

Write the packet so the reviewer can reproduce your tests and attack the
implementation without needing your private reasoning.

==================================================
FINAL RESPONSE
==================================================

After completing work, respond with:

1. concise summary
2. Core repo URL
3. HA repo URL
4. original/final SHAs for both
5. Docker/DB startup status
6. Tule Elk parity status
7. Condor parity status or reason deferred
8. exact test results
9. CI status
10. backup/restore status
11. review-packet location
12. any blocker or unresolved decision

Then end EXACTLY with:

READY FOR INDEPENDENT MILESTONE 1 REVIEW