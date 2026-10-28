# Batch 2A deployment candidate — awaiting review and approval

Batch 2A R1–R3 has the user's supplied independent Claude PASS at accepted code
`10bde5f0dcb57821f36a971af9e3dc4183271202`; prior evidence tip
`4d7fa28001c0f71a429e3b40e9a0ed27a15179ad`.
Starting Core main/origin for deployment preparation equals that evidence tip.
Starting HA main/origin: `a958ab2e3e0e1ec44f4d246b3471bd0d1faaac73`.

Proposed releases, neither created nor published:

- Core GitHub prerelease `v0.1.0-rc.3`, Linux AMD64 GHCR runtime.
- HA beta `v0.17.0-dev.4`, explicitly compatible with API v1/engine 0.1.0-dev,
  schemas 0008/0009/0010.

The implementation commits and CI receipts are recorded in the final review
handoff after validation. No draft release, tag, image publication or installed
Unraid/HA change is authorized by this preparation pass.

## Verified configuration and data boundaries

Use the complete [image-only Compose stack](../compose.unraid.yaml) and
[matching environment template](../.env.unraid.example). The current stack already
passes `CORE_COLLECTION_SCOPE_JSON` (default `{}`) and `CORE_SOURCE_HISTORY`
(default `true`). Preserve the operator's actual scope/history range and every
existing secret, path, stack/project name, LAN binding, network and health check.
Keep `CORE_SOURCE_KEYS=all`, `CORE_PATTERNS_MODE=shadow`, existing retention policy,
and historical collection enabled. Do not reset a checkpoint to make a poll look
new. All 81 inventory entries remain, including pending sources and credentials.

Core runtime/collectors/intelligence/migrations are unchanged from the accepted
Batch 2A code. This pass adds deployment evidence only: fresh image-only startup
reads the actual runtime settings, and the disposable 0009→0010 check snapshots
all application base tables (excluding migration metadata and static PostGIS
reference rows). Every existing column/value, privacy/revision row and database
owner must match after migration. A nonempty lease/checkpoint/backoff sentinel
must survive; it is removed only after verification, within that test database.
The new nullable native timestamp starts NULL and environmental history starts
empty; no historical measurements are manufactured by migration.

`tools/verify_schema0010_upgrade.py` refuses non-CI or non-`*_test` targets.
All migration, restore, role and image-stack checks run on disposable GitHub
runners. No test connects to the installed Unraid database. API/HA compatibility
captures use pinned Core ASGI routes with explicitly synthetic upstream test
data, not a live provider or assessment publication.

## Operator procedure — only after independent review and explicit approval

1. Save verified PostgreSQL 0009 backups and the working Compose/.env through the
   existing backup process. Preserve HA configuration/Store and installed versions.
   Do not proceed without a usable matching restore point.
2. Publish the approved HA beta and install it through HACS with prereleases
   enabled. Restart HA and refresh the dashboard. It still accepts the currently
   installed Core schema 0009. Retain the same entry/origin/token and entity IDs.
3. Publish the approved Core GitHub prerelease at its reviewed exact commit.
   Its release workflow must validate that commit, build the runtime on GitHub,
   publish version/SHA/preview tags and verify anonymous GHCR pulls. A main push
   cannot publish. `latest` must remain untouched. No image exists for rc.3 yet.
4. Once publication and public pull receipts pass, open the existing Photography
   Events stack in Unraid Compose Manager. Keep `CORE_IMAGE=...:preview` for the
   existing manual channel, or pin the approved `...:v0.1.0-rc.3` using the UI.
   Merge the two collection settings if the installed stack predates Batch 2A;
   preserve their existing operator values when present.
5. Select **Pull & Up** and wait for Core to become **healthy**. Do not build on
   Unraid, add a checkout, schedule automatic updates, delete PGDATA or rotate
   passwords. Subsequent channel updates remain the same UI-only action.
6. Operator-run installed verification checks readiness/API v1/schema 0010,
   app role separation, original records/revisions and restored checkpoints,
   retained lease/backoff deadlines, per-station current/history diagnostics,
   actual native numerical values/units and freshness. Observe automatic polling
   and historical progress; empty or stale stations must stay explicit. NPS
   credential verification remains pending by the user's prior choice.
7. HA must reconnect without recreating the entry. Confirm unavailable/held/stale
   states, withheld destinations and disabled notifications. Successful readiness
   does not approve intelligence or prove fresh provider coverage.

Schema 0010 is forward-only. Never point an older 0009 image at an upgraded
database. Recovery requires the matching image/configuration and a verified
pre-upgrade database backup restored by the operator, plus the HA backup if its
config/Store migration needs reversal. Preserve the upgraded volume/backup first.

## Approval and next work

Stop after implementation/testing and the independent-review handoff. Publication
and installed changes each need explicit user approval. No production opportunity
promotion, notification, new HA intelligence or source adapter is included here.
Batch 2B (weather/satellite/fog/atmosphere ingestion) resumes after the approved
deployment is ready. Its full source scope remains the existing 81-key registry;
this document does not start that batch or narrow its inventory.
