# Photography Events Core — Milestone 2 shadow development

A LAN-only Python service for the Photography Events regret-prevention product.
The Home Assistant v0.16.1 local engine remains authoritative. Core is a
foundation and deterministic Carrizo Plain Tule Elk parity slice, not a public
release or a replacement for the existing integration.

The accepted [Milestone 1 review](IMPLEMENTATION_REVIEW_MILESTONE_1.md) records
the foundation. The [Milestone 2 review](IMPLEMENTATION_REVIEW_MILESTONE_2.md)
records observation intelligence, shadow activation, acceptance and limitations.

HA repository: https://github.com/Tmatz27/Home-assistant-photography-events

```
explicit synthetic fixture
  -> source attempt -> raw record -> normalized species assertion
  -> versioned Carrizo definition -> opportunity + material revisions
  -> PostgreSQL 18 / PostGIS 3.6 -> async REST v1
  -> optional HA async client + HA Store (developer scaffold)

production today: HA local engine -> existing entities/websocket -> bundled card
```

## Requirements and Unraid installation

Use Docker Engine with Compose v2 and a local cache/appdata filesystem suitable
for PostgreSQL. Only two services run: `photography-events-core` and the dedicated
`photography-events-db` (`postgis/postgis:18-3.6`). No other application's database
is reused. Database port 5432 is not published in production Compose.

1. Clone this repository under `/mnt/cache/appdata/photography-events-core/repo`.
2. Create `/mnt/cache/appdata/photography-events-db/` and
   `/mnt/cache/appdata/photography-events-core/`. Use cache storage, not `/mnt/user`
   for the active DB. Paths can be changed with `DB_DATA_PATH` and `CORE_DATA_PATH`.
3. Copy `.env.example` to `.env`. Generate **three separate** random secrets (for
   example, `openssl rand -hex 32`) for `POSTGRES_ADMIN_PASSWORD`,
   `POSTGRES_PASSWORD`, and `CORE_API_TOKEN`. Do not commit or print `.env`.
4. Set `CORE_BIND_IP` to the Unraid host's LAN IP, `CORE_PORT=8099`, and
   `CORE_DATABASE_TIMEOUT=3`. Default binding is loopback for safe development.
   Set `BACKUP_DIR` to the existing mounted Synology backup directory.
5. Run `docker compose config -q`, then `docker compose up -d --build --wait`.
6. Check `http://<LAN-IP>:8099/health/live` and `/health/ready`.

No public listener, proxy tunnel, Cloudflare exposure or router port forwarding
is part of this setup. Both services share an internal Compose database network;
Core also has a separate bridge network. The API binding is the only host port.

The [PostGIS image's PostgreSQL 18 volume contract](https://github.com/postgis/docker-postgis)
mounts **`/var/lib/postgresql`**, with PGDATA below `18/docker`. Mounting only the
old `/var/lib/postgresql/data` location would fail to preserve the intended data.

The image initializes PostGIS, then `scripts/20-app-user.sh` creates the dedicated
non-superuser application role `photography_events`. Core connects using that
role; the admin password stays in the DB container. Initialization scripts only
run on an empty volume. Changing `.env` does not rotate an existing DB password.

Core runs as UID 10001. It does not need to write its appdata mount in M1; all
application state is in PostgreSQL. Both services use `unless-stopped` restart
policies. Compose gates initial Core startup on DB health. Alembic runs before
Uvicorn; migration failure stops startup with a sanitized structured event.

## Configuration

| Variable | Meaning |
|---|---|
| `POSTGRES_ADMIN_PASSWORD` | DB initialization/admin secret, DB container only |
| `POSTGRES_PASSWORD` | Dedicated application role secret |
| `CORE_API_TOKEN` | Generated bearer secret, at least 32 characters |
| `CORE_BIND_IP` / `CORE_PORT` | LAN binding; default `127.0.0.1:8099` |
| `CORE_DATABASE_TIMEOUT` | Whole DB operation deadline, default 3 seconds |
| `CORE_EVALUATION_GRACE` | Grace for materially newer relevant inputs; default 30 seconds, range 0–300 |
| `CORE_PATTERNS_MODE` | `off` by default; `shadow` computes development intelligence after M1 commits, with no production promotion |
| `CORE_PATTERN_TIMEOUT` | 30 seconds per shadow phase; separate from the M1 database deadline |
| `DB_DATA_PATH` | Default `/mnt/cache/appdata/photography-events-db` |
| `CORE_DATA_PATH` | Default `/mnt/cache/appdata/photography-events-core` |
| `BACKUP_DIR` | Mounted Synology destination, no NAS credentials in Core |
| `CORE_DATABASE_URL` | Optional development asyncpg URL, replaces host/password fields |
| `DB_HOST` / `POSTGRES_DB` | Internal host / DB override for isolated restore validation |
| `CORE_TEST_DATABASE_URL` | Destructive tests only; DB name must end in `_test` |

`.env` supplies Compose interpolation; secrets are explicitly passed only to the
service needing them. Uvicorn access logging is disabled and API errors never
serialize exceptions or connection strings. Application logging uses stable
JSON event codes (startup, schema, DB loss/recovery, collection/parser/scheduler,
source stale, API/auth, parity failures).

## API and health

Public `GET /health/live` checks process liveness only. Public
`GET /health/ready` checks DB connectivity, Alembic revision `0006`, PostGIS 3.6,
and application relations; failure is 503. Stale providers do not make the
database unready. Both return `core_version`, `api_version`, and `schema_version`.

Data endpoints require `Authorization: Bearer <CORE_API_TOKEN>` using
constant-time comparison independent of PostgreSQL:

- `GET /api/v1/opportunities`: optional `presentation` and `category` filters.
- `GET /api/v1/opportunities/{occurrence_key}`: one known occurrence, or 404.
- `GET /api/v1/sources/health`: derived UP/STALE/DOWN source state.

List responses contain `assessment_id`, `generated_at`, `data_as_of`, `assessment_state`,
`missing_required_sources`, `degraded_sources`, version metadata, and typed
`items`. A successful empty, current assessment is different from an unassessed
or failed cycle. Database failures always return 503, never `items: []`.
List and detail read one current generation; each item carries its `assessment_id`.
An occurrence outside that generation returns 404. Expired or outdated decisions
are projected as held/ineligible, even on detail lookup. Equal-watermark input
conflicts and corrupt stored products return sanitized 503 responses.
Errors use `{"error":{"code":"...","message":"..."}}`; invalid filters are
422, invalid tokens 401. Additive API fields are allowed for HA compatibility.

OpenAPI is generated from Pydantic models with `create_app().openapi()`. It is
validated in CI; interactive documentation endpoints are not exposed.

**M1 scope of “complete” is the installed Tule Elk slice only**, not all of the
HA product. The synthetic source adapter is explicitly labelled in source names.
No fixture data is seeded at startup and there are no live collectors. To
exercise the persisted slice deliberately:

```sh
docker compose exec photography-events-core python -m pec tests/fixtures/legacy_tule_elk.json
```

This imports frozen September 2026 data, not current wildlife intelligence.
At today's clock it may correctly be held/stale. The API never renews evidence
just because a fixture or provider record was fetched again.

## Database, migrations and provenance

Revisions `0001` and `0002` remain unchanged. Revision `0002` provides immutable
assessment generations ([schema](docs/SCHEMA_0002.md)); revision `0003` adds
correctable report membership, canonical behavior, immutable analytical clusters
and persistent episodes ([schema](docs/SCHEMA_0003.md)). Revision `0004` adds
independent shadow-run lifecycle metadata ([schema](docs/SCHEMA_0004.md)). Revision
`0005` adds final identity/behavior corrections and coherence diagnostics
([schema](docs/SCHEMA_0005.md)). Revision `0006` adds three indexes for bounded
identity dependency/correction lookups ([schema](docs/SCHEMA_0006.md)); no new
tables or analytical policy changes are introduced.
SQLAlchemy provides bounded async connection pooling and transactions; no ORM
objects cross the API. PostGIS types, the GiST index and extension are written
manually. Alembic controls revision order and transactional application.
`python -m alembic upgrade head` is repeat-safe. Take and verify a backup before
upgrading. Revisions `0002` through `0006` are forward-only; earlier schemas
cannot represent their histories; rollback requires a verified pre-upgrade backup restored to a new DB
and the pre-upgrade application image. The disposable `0001` downgrade/upgrade
check remains in CI. Migrated decisions stay incomplete/held until a fresh
newer assessment supplies verified source provenance.

High-volume row IDs use BIGINT identity. Deterministic occurrence identity is
`tule_elk_rut-<original-window-start>` from legacy `active_windows` and `event_id`.
Source-controlled JSON definition data plus Python decision/safety/spatial and
ingestion code produce the SHA-256 definition hash. The DB stores rule key/version/hash and
engine version, never executable policy blobs.

Raw exact geometry is restricted ingestion data; normalized analysis/public
geometry are separate. The installed Tule Elk policy permits protected exact
points for internal analysis. Protected public points are NULL, and automatic
provider updates cannot reduce protection. API locations come exclusively from
the curated public Carrizo site.
Locations accept arbitrary EPSG:4326 Geometry for future polygons. Observations
use Point. The GiST index supports local evidence queries; metric tests cast to
geography rather than treating degrees as metres. No clustering is implemented.

Source attempts append; successful retries retain failed attempts. Current
health is a SQL view plus versioned freshness policy. Collection commits
separately from assessment publication. Provider content changes supersede old
normalized assertions; evaluation selects all eligible current stored assertions,
including incremental batches and future records once their time window opens.
Stable-ID fixture records without IDs are rejected individually.

A locked singleton pointer publishes an immutable generation atomically. Only
newer `data_as_of` advances it; equal inputs are idempotent and equal timestamps
with different fingerprints fail closed. Fingerprints exclude database row IDs
and fetch times. Evidence and material revisions reference the exact generation
item. Required/consulted source-run provenance detects materially newer relevant
inputs after the configured grace; unrelated source updates do not degrade it.
Collection success cannot mask generation failure. Route baseline uniqueness is enforced;
the slice retains the legacy calibrated drive estimate. No live routing provider
is connected and no estimated route is described as routed.

`scheduler.py` provides a single-process, non-overlapping asyncio framework with
timeouts, Retry-After, bounded exponential backoff, jitter and shutdown. All
ordinary collector exceptions advance backoff; cancellation propagates. Invalid
Retry-After values are ignored and extreme delays are clamped to a bounded
policy (default one day). Live backoff survives state-store failure. No jobs are
registered at startup. `source_backoff` persists restart state through load/save
callbacks. Multiple Core replicas are not supported in M1.

The DB guard covers reads, writes and pool checkout. On deadline it terminates
the tracked asyncpg connection before cancellation can block in rollback/close.
Frozen-DB CI checks concurrent warm-pool and cold-connect requests, bounded 503
responses, zero checked-out connections and recovery after unpause.

`retention.sweep` is an explicit bounded maintenance operation: redact raw
payloads after 90 days, prune only unreferenced old source runs, retain evidence
identities and revisions. It is not VACUUM and is not yet scheduled automatically.
Later source-specific retention and longer normalized-data policies need actual
volume measurements. No partitioning or bulk imagery retention is implemented.

## Backup and restore

Run both operator scripts from the Core repository directory containing
`compose.yaml` and the intended `.env`; they use that Compose project context.

Run nightly from the existing Unraid scheduling mechanism, with `BACKUP_DIR`
exported to the mounted Synology destination:

```sh
BACKUP_DIR=/path/to/mounted/synology sh scripts/backup.sh
```

The command is `docker compose exec -T photography-events-db pg_dump -U postgres
-d photography_events -Fc --no-acl`. The script writes a mode-restricted
`.partial` file and renames it only after success; a shell trap removes partial
files on failure or interruption. A backup contains potentially
sensitive ingestion data; protect the NAS destination accordingly.

Restore only to a **new** compatible database:

```sh
sh scripts/restore.sh /path/to/backup.dump photography_events_restore_test
docker compose run --rm --no-deps -p 127.0.0.1:8100:8099 \
  -e POSTGRES_DB=photography_events_restore_test photography-events-core
```

The script creates the DB owned by the application role, enables PostGIS,
restores as the DB administrator with `pg_restore --no-acl --exit-on-error`, and
runs migrations. Preserve archive ownership: app tables remain owned by the
non-superuser application role, while image-supplied extensions are recreated by
the administrator. A compatible destination must have both configured roles.
Verify restored readiness and the occurrence API before
planning any cutover. The script refuses production/reserved names and existing
destinations; it never drops or overwrites a database.

`tools/acceptance.py` demonstrates custom-format backup, clean restore, migration
checks and a newly started Core against restored data. Results and exact sizes
are written to `evidence/acceptance.json` and uploaded by CI.

## Development and parity

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.lock
export PYTHONPATH=src
python -m pytest -q
python -m ruff check src migrations tools tests
python -m compileall -q src migrations tools
python -m alembic upgrade head --sql
# With valid environment and migrated DB:
python -m uvicorn pec.api:create_app --factory --host 127.0.0.1 --port 8099
```

The runtime and development lockfiles pin direct and transitive dependencies.
FastAPI/Pydantic define the contract, SQLAlchemy/asyncpg provide async PostgreSQL,
Alembic manages explicit migrations, Uvicorn serves ASGI. No GeoAlchemy dependency
is needed because spatial SQL is explicit. asyncio avoids another scheduler
dependency. pytest and Ruff are the only Core testing/lint tools.

The parity fixture was **executed** against HA SHA
`4905e35c0668c37737d84685e65d2a806f7c92f7`; inputs are synthetic and outcomes come
from the real legacy engine. Regenerate with the pinned checkout and its bs4
dependency: `python tools/capture_legacy_parity.py --legacy-repo ../Home-assistant-photography-events`.
The capture script never imports Core. Core evaluates the same logical inputs
through its own phenomenon layer. The normalization compares decision semantics,
converting `watch` to `watching` and equivalent UTC timestamp serialization.

The current fixtures cover 15 Tule Elk cases and 24 fields, including occurrence,
dates, eligibility, presentation, separate scores, drive, safety/access, evidence,
reason/awaiting, Can't Miss, Watching and gear. The legacy 14-day presence horizon
is preserved (its seven-day definition limit applies to behavior reports). The
legacy September 15–October 10 window and policy text are preserved, including
the NPS Point Reyes reference inherited by the Carrizo rule; the location remains
Carrizo and has not been replaced by Point Reyes. Behavior-report parser migration
and any scientific-policy correction require a separate intentional change.

CI also independently recaptures nine raw-to-API pipeline cases, including
private geometry, future admission without refetch, provider corrections and
legacy grouping. It executes 18,000 seeded evaluator comparisons with zero
mismatches. See the correction review section and its committed CI artifacts
for exact test counts and environments.

## Observation intelligence: explicit shadow mode

The [FINAL INDEPENDENT CORRECTION PASS](IMPLEMENTATION_REVIEW_MILESTONE_2.md#final-independent-correction-pass)
is the current boundary review. Episode matching and prior revision reads are
prepared before locking the M1 pointer. Final publication rechecks the registry
and uses transaction-local lock_timeout=500ms, statement_timeout=750ms and
PostgreSQL18 transaction_timeout=900ms at default settings, plus a one-second
client guard. Smaller settings scale all server bounds below the finish budget,
which is capped by one third of the M1 deadline. Cancellation
propagates after bounded cleanup. M2 source provenance records inputs actually
consumed, which may have been collected after its base M1 assessment committed.

Bear fixture policy explicitly configures a stricter 1,000 m coherence fallback
(primary 3,000 m). Only a rejected candidate gets one second DBSCAN pass; every
normal gate is reapplied. No implicit epsilon, third pass or recursion exists.
Authenticated debug records coherence_rejected and fallback outcome. Nonsensitive
candidate counts/radius/diameter may be inspected; protected metrics are withheld,
and no centroid/point geometry is emitted.

SQL input admission has a policy-derived broad temporal bound before narrower
Python filtering. Count requirements must be positive; NULL is unknown.
Qualified mirror claims are validated against taxon/time; mismatches keep
independent identity and sanitized provenance. The fixture time tolerance is one
hour and is not fuzzy deduplication or geographic proof. Historical bugling is
backfilled to canonical rut by migration0005. Policies remain fixture-only and
biologically unvalidated; M2 remains default-off/shadow-only.


The [required S1 correction review](IMPLEMENTATION_REVIEW_MILESTONE_2_CORRECTIONS.md)
records the independent publication boundary. M1 generation returns after its
own commit; its fingerprint excludes shadow policy/engine/input metadata. A
background task uses a separate one-connection pool and shadow deadline. Input
capture, clustering, destination checks and bulk artifacts run without the M1
publication lock. A short transaction verifies the current assessment equals
the base before publishing episode changes, otherwise marks the run superseded.
Pending/failed runs expose no current shadow artifacts; M1 remains valid.

For an explicit fixture script that needs completed shadow output, call
`await db.wait_for_patterns()` after generation. Production generation does not
await this drain. `db.close()` cancels outstanding tasks and disposes both pools.
An abrupt process crash may leave a run marked running; no durable worker or
automatic retry has been added. This affects shadow coverage only.

Set `CORE_PATTERNS_MODE=shadow` in `.env` and recreate Core to compute M2 after
an M1 assessment commits. The default remains `off`. Nothing is seeded at startup. Use the
existing explicit synthetic fixture import to supply records; the M2 test
fixtures construct local synthetic provider mirrors, never new live collectors.

M1 collection persists raw/normalized assertions and commits without report-group,
membership or behavior-relationship work, in both OFF and SHADOW modes. It retains
cheap fixture-contract validation and the original M1 behavior field. Enrichment
is deferred until a shadow pattern run captures its inputs. That bounded repeatable-
read transaction reconciles the active policy window plus exact identity
dependencies and behaviors in batches, then
records the deterministic input fingerprint and consumed source-run provenance.
An enrichment failure rolls back that shadow phase and marks the run failed;
it cannot roll back M1 collection. A running run with no input fingerprint has not
completed enrichment/capture. No partially reconciled set is used for clustering.
Server-local enrichment limits also bound locks on shared assertion metadata.

The working window uses the maximum temporal window and future tolerance of the
run's enabled policies. Relevant mirrors load their canonical targets even outside
that window; relevant corrected canonical records load older explicit claimants
from durable metadata, including rejected/rehomed claims. Lookups use qualified
IDs, never nearby coordinates, species or time as identity discovery. Unrelated
older current assertions remain stored and are not reconciled or retired by age.
The logical input fingerprint includes the used observations and identity
dependencies; full source-run hashes remain separate consumed provenance.
Persistent identity mismatches log on status change, with a resolution event when
they become valid.

Rejected explicit origin claims remain in the raw metadata contract and are retried
when either side is relevant, even without mirror redelivery. Retention removes bulk
provider text but preserves a small metadata envelope for explicit claims/report
aliases. Historical membership links used by clusters remain immutable.

The pipeline is current normalized assertions → atomic M2 enrichment → qualified report identity →
policy-specific temporal/precision admission → report-level DBSCAN → coherent
clusters → continuing pattern episodes → held developer opportunity previews.
Same provider ID upserts once; only trusted fixture-adapter qualified origin IDs
merge mirrors. No fuzzy deduplication occurs. Membership corrections preserve
the exact historical links used by earlier clusters. Explicit canonical behavior
is queryable separately from raw text; presence never implies feeding or cubs.

Policies in `src/pec/patterns/policy.py` are provisional architectural fixtures.
They use EPSG:3310 projected meters for the California operating envelope;
storage remains EPSG:4326. Meter units do not imply exact geodesic distance.
One deterministic representative per independent report enters ordered DBSCAN.
Unknown accuracy, area locations and excessive uncertainty stay outside density
and centroid calculations. Regional signals cannot satisfy tight thresholds.
Incoherent candidates exceeding the enclosing-circle diameter limit are rejected.
Their episode transition applies only to related prior support or a candidate
passing the existing spatial/temporal continuation test, never every episode of
the same phenomenon. The configured single dense-core rescue remains unchanged.
Animal counts use the largest single report, never a sum or an exact population.

Clusters and episode snapshots are generation-scoped; previous history survives
recomputation. Episode identity persists in PostgreSQL across restarts. At most
one cluster continues a given episode per generation; additional compatible
clusters record child lineage. Automatic merge requires explicit policy and
unambiguous evidence continuity. Expired episodes never automatically reopen.
Policy changes end/restart episodes conservatively. Source-controlled policy
hashes and analytical engine source hashes make the calculation inspectable.

Authenticated `GET /api/v1/debug/patterns` and its `/{episode_key}` detail route
return redacted summaries, cluster diagnostics and held previews from one current
assessment. They expose no raw records, internal centroids or radii. Sensitive
metrics, behaviors and named locations are withheld; private analysis still
participates internally. Only explicitly approved source-controlled destination
relationships may produce public previews; no nearest-location fallback exists.
All previews remain ineligible with unknown travel checks. Debug APIs are never
consumed by the HA card or developer bridge.

Normal `GET /api/v1/opportunities` retains accepted M1 decisions and permits an
optional nullable `pattern_episode_id` in the model. There is no production M2
promotion mode. Raw ordinary observations do not become Core product rows;
pattern summaries are inspected only in the explicit developer path until review.

## Limitations and deferred scope

Core has no production collectors or HA UI cutover. Pinnacles Condor is deferred:
its independent count/behavior evidence paths, NPS access, public-site encounter
classification need their own complete parity fixture set before porting. Its
legacy `now.date()` identity can reset Follow/Skip/Seen during a continuous
spectacle. The deferred design is an episode key based on phenomenon + site +
episode_start, continued by qualifying fresh evidence. Do not blindly port the
daily key. No Condor implementation or episode behavior is added in M1.

No map, new live source family, iGPU/OpenVINO or `/dev/dri`, Redis/worker
service, machine learning, broker, TimescaleDB, public API or v0.17 release has
been added. The detailed implementation review packet records actual acceptance
results and remaining limitations; do not infer operational completion from this
README alone.
