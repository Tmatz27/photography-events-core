# v0.1.0-rc.2 — manual release deployment

Approved pre-release deployment infrastructure for Photography Events Core on
Unraid. This does not complete the 81-entry source ingestion phase, enable
production opportunity intelligence, or accept installed Unraid collection.

Images are built on GitHub Actions only after the exact release commit passes
the complete validation suite and the runtime image passes image-only stack,
fresh PostGIS initialization and existing-volume preservation checks. GHCR
version/SHA tags identify the exact commit; `preview` follows approved
pre-releases. This pre-release does not create or replace stable `latest`.

Use attached `compose.unraid.yaml` and `.env.unraid.example` in Unraid Compose
Manager. Retain your existing credentials, stack name, LAN binding and cache
appdata paths. Back up the existing database before the one-time stack migration.
The self-contained init hook removes the Git-checkout script mount, preserves
PostgreSQL 18/PostGIS 3.6 and existing roles/data/passwords, and initializes the
non-superuser application role for fresh installations.

Normal updates: open the Photography Events stack → **Pull & Up** → wait for
**healthy**. No Git checkout, local build, main-push deployment, hourly updater or
automatic replacement of the running Unraid container. Continue ingestion in
shadow mode with `CORE_SOURCE_KEYS=all`; no source/engine/HA changes in this release.

First GHCR publication requires making the linked package Public once. Release
readiness requires the workflow's successful anonymous pull and pulled-image
verification, not merely successful publishing. See
[release and update instructions](https://github.com/Tmatz27/photography-events-core/blob/v0.1.0-rc.2/docs/RELEASE_DEPLOYMENT.md).
