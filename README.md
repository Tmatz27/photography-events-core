# Photography Events Core — Milestone 1 development

A LAN-only Python service for the Photography Events regret-prevention product.
The Home Assistant v0.16.1 local engine remains authoritative. Core is a
foundation and deterministic Carrizo Plain Tule Elk parity slice, not a public
release or a replacement for the existing integration.

Read the [Milestone 1 implementation review](IMPLEMENTATION_REVIEW_MILESTONE_1.md)
for the exact scope, deviations, provenance and verified acceptance results.

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
`GET /health/ready` checks DB connectivity, Alembic revision `0001`, PostGIS 3.6,
and application relations; failure is 503. Stale providers do not make the
database unready. Both return `core_version`, `api_version`, and `schema_version`.

Data endpoints require `Authorization: Bearer <CORE_API_TOKEN>` using
constant-time comparison independent of PostgreSQL:

- `GET /api/v1/opportunities`: optional `presentation` and `category` filters.
- `GET /api/v1/opportunities/{occurrence_key}`: one known occurrence, or 404.
- `GET /api/v1/sources/health`: derived UP/STALE/DOWN source state.

List responses contain `generated_at`, `data_as_of`, `assessment_state`,
`missing_required_sources`, `degraded_sources`, version metadata, and typed
`items`. A successful empty, current assessment is different from an unassessed
or failed cycle. Database failures always return 503, never `items: []`.
Expired decisions are projected as held/ineligible, even on detail lookup.
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

`migrations/versions/0001_schema.sql` is the explicit schema model and inventory.
SQLAlchemy provides bounded async connection pooling and transactions; no ORM
objects cross the API. PostGIS types, the GiST index and extension are written
manually. Alembic controls revision order and transactional application.
`python -m alembic upgrade head` is repeat-safe; downgrade is destructive and is
only exercised against disposable test databases.

High-volume row IDs use BIGINT identity. Deterministic occurrence identity is
`tule_elk_rut-<original-window-start>` from legacy `active_windows` and `event_id`.
Source-controlled JSON definition data plus Python decision/safety/spatial code
produce the SHA-256 definition hash. The DB stores rule key/version/hash and
engine version, never executable policy blobs.

Raw exact geometry is restricted ingestion data; normalized analysis/public
geometry are separate. Sensitive fixture locations have no analysis/public
point. API locations come exclusively from the curated public Carrizo site.
Locations accept arbitrary EPSG:4326 Geometry for future polygons. Observations
use Point. The GiST index supports local evidence queries; metric tests cast to
geography rather than treating degrees as metres. No clustering is implemented.

Source attempts append; successful retries retain failed attempts. Current
health is a SQL view plus versioned freshness policy. One raw record can produce
multiple normalized assertions. Strict observation/context association tables
preserve evidence provenance. Material decision changes append typed revisions;
unchanged polling does not add snapshots. Route baseline uniqueness is enforced;
the slice retains the legacy calibrated drive estimate. No live routing provider
is connected and no estimated route is described as routed.

`scheduler.py` provides a single-process, non-overlapping asyncio framework with
timeouts, Retry-After, bounded exponential backoff, jitter and shutdown. No jobs
are registered at startup. `source_backoff` can persist restart state via the
load/save callback interface. Multiple Core replicas are not supported in M1.

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
`.partial` file and renames it only after success. A backup contains potentially
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

## Limitations and deferred scope

Core has no production collectors or HA UI cutover. Pinnacles Condor is deferred:
its independent count/behavior evidence paths, NPS access, public-site encounter
classification and daily occurrence identity need their own complete parity
fixture set before porting. Its daily key currently includes `now.date()` in
legacy `birds._spectacle_row`; do not silently replace that with an annual key.

No DBSCAN, Map, new live source family, iGPU/OpenVINO or `/dev/dri`, Redis/worker
service, machine learning, broker, TimescaleDB, public API or v0.17 release has
been added. The detailed implementation review packet records actual acceptance
results and remaining limitations; do not infer operational completion from this
README alone.
