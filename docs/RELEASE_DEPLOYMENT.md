# Manual GitHub Release → GHCR → Unraid Compose Manager

Development pushes still run complete CI. They never publish a deployment image.
Only publishing a reviewed GitHub Release triggers `release.yml`. The workflow
resolves the exact tag commit, runs the existing complete validation workflow
against that SHA, builds the existing `runtime` Dockerfile target for Linux AMD64,
tests the actual image-only stack with fresh and existing PostgreSQL volumes,
then pushes that tested image using `GITHUB_TOKEN` with `packages: write`.
Failed validation or stack testing prevents image publication.

## Release tags and approval

- `ghcr.io/tmatz27/photography-events-core:vX.Y.Z`: approved stable version.
- `ghcr.io/tmatz27/photography-events-core:v0.1.0-rc.2`: initial approved pre-release.
- `ghcr.io/tmatz27/photography-events-core:sha-<full-40-character-commit>`:
  immutable traceability tag; the workflow refuses replacing existing version/SHA tags.
- `latest`: only a published stable release without a prerelease suffix/flag.
- `preview`: only a published approved pre-release; supports manual UI updates
  during unfinished ingestion development. A pre-release never changes `latest`.

Version/SHA tags identify a fixed release. Choose a channel for the three-step UI
update procedure below. A deliberately pinned version requires selecting a new
version in Compose Manager's environment editor before pulling that version.
There is no push-to-main deployment, Watchtower, hourly update, server Git
checkout, automatic container replacement or production intelligence promotion.
The initial pre-release is deployment/ingestion infrastructure, not acceptance of
the complete 81-entry ingestion program or a production opportunity engine.

Maintainer procedure: finish review, choose a new semantic version and exact
reviewed commit, open GitHub Releases → Draft a new release, create/select its tag
at that commit, mark RC versions **pre-release**, then publish. Do not move tags.
Wait for both exact-commit validation and release publishing/public-pull workflow
jobs to pass before offering the version for deployment. No local build is needed.

## One-time GHCR public visibility

GitHub packages initially default to private even for a public repository.
After the first push, the owner opens GitHub profile → Packages →
`photography-events-core` → Package settings → Danger Zone → Change visibility
→ Public, and confirms the package name. Keep repository linkage and Actions
write access. Public container packages can then be pulled anonymously from
Unraid; no PAT, GitHub password, `docker login` or GHCR credentials in `.env`.
See [GitHub's registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
and [visibility instructions](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).

The `verify-public` job uses a fresh empty Docker configuration and actually
pulls the version, SHA and channel tags with no login. It checks their digest and
tests the pulled image. If initial visibility is not changed within its retry
window, the release is **not ready**. Change visibility, then use GitHub Actions
**Re-run failed jobs** (only public verification). Do not rebuild/replace the
already published immutable version. Publication alone is not a verified pull.

## One-time Compose Manager migration / fresh installation

Use the complete `compose.unraid.yaml` and matching `.env.unraid.example` from
the release. Copy/paste them into the **existing Photography Events stack** in
Unraid Compose Manager; retain its stack/project name. Keep the working `.env`
secrets, provider keys, LAN IP/port, backup destination and path overrides;
merge the new `CORE_IMAGE` field instead of replacing existing credentials.
Use `CORE_IMAGE=ghcr.io/tmatz27/photography-events-core:preview` for the approved
initial RC. Set/retain `CORE_SOURCE_KEYS=all`, `CORE_PATTERNS_MODE=shadow` and
`CORE_LIVE_SOURCES=true`; retention remains your existing explicit choice.
Once stable release deployment is independently approved, select `:latest` in
this same UI to follow approved stable releases. Both channels are manual pulls.

Before switching an existing installation, take the existing PostgreSQL backup
and preserve the current `.env` and stack configuration. Do not delete/reinitialize
its appdata directory. No existing database password is changed by editing `.env`.
Fresh installs need separate generated admin/application/API secrets and the
existing cache appdata directories. No Git checkout or downloaded script is needed.

The stack preserves these default paths:

- `/mnt/cache/appdata/photography-events-db` → `/var/lib/postgresql`, including
  PostgreSQL 18's `18/docker` PGDATA subdirectory.
- `/mnt/cache/appdata/photography-events-core` → `/var/lib/photography-events-core`.

Database image remains `postgis/postgis:18-3.6`, with no published database port.
The internal database network, separate API network, LAN binding, service names,
restart policies, health checks and dependency gating are unchanged. Keep the
existing stack name so its Compose network names stay consistent.

The database entrypoint writes its application-role init hook **inside the image's
ephemeral container filesystem** and then execs the official PostGIS/PostgreSQL
entrypoint. PostgreSQL runs this hook only on an empty volume, after PostGIS init.
It creates the application database owner with LOGIN and explicit non-superuser,
non-creation/non-replication privileges. Existing PGDATA, roles and passwords are
left intact on every pull/recreate. The admin password remains DB-only; Core
runs UID 10001 and connects as `photography_events`. There is no bind mount from
`/mnt/cache/appdata/photography-events-core/repo` and no destructive SQL.

## Every normal release update — UI only

1. Open the **Photography Events** stack in Unraid Compose Manager.
2. Select **Pull & Up**.
3. Wait for the updated Core container to become **healthy**.

`pull_policy: always` fetches the selected approved release channel when you
perform this action. Nothing schedules it or replaces the running container
before you select it. Health readiness verifies connectivity and migrations;
provider freshness/collection evidence remains a separate installed verification.
If a migration fails, Core fails closed. Keep the backup; restoring a database is
an explicit operator recovery step, never an automatic image downgrade.

## Verification receipts

The original `v0.1.0-rc.1` publication gate caught a runner-owned evidence-directory
bug before any application image was pushed. Its release/tag remains at the
original SHA as a failed attempt. The corrected first deployment image is
`v0.1.0-rc.2`; no published image or immutable tag was overwritten.

Complete development/release validation includes the historical 491 accepted
cases, portable tests, Ruff, migrations, independent M1 byte parity and 18,000
comparisons, DB restart/restore and all accepted privacy/safety/shadow boundaries.
New release gate tests and disposable fresh/existing-volume stack checks add
deployment coverage. No source adapter, intelligence, HA or inventory changes.
The release workflow emits `release-stack-candidate` and `release-publication`
artifacts with exact revision, Linux AMD64 image identity/digest, non-superuser
ownership and preserved existing-volume data. No credentials are recorded.
Actual first-publication image/tag/digest and anonymous-pull receipts are recorded
after successful publication; instructions alone do not certify deployment readiness.
