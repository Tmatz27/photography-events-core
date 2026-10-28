# Batch 2A deployment — independent review request

Review these exact unpublished candidates, without publishing or changing an installed system:

| Repository | Starting main | Candidate code freeze | Proposed prerelease |
| --- | --- | --- | --- |
| Core | `4d7fa28001c0f71a429e3b40e9a0ed27a15179ad` | `7d5f2432e0a4fa797b78d298e954d4d07fe1f754` | `v0.1.0-rc.3` |
| HA | `a958ab2e3e0e1ec44f4d246b3471bd0d1faaac73` | `5497a6cc36019f4c4bdd0e23db88675be9a896eb` | `v0.17.0-dev.4` |

Core CI: https://github.com/Tmatz27/photography-events-core/actions/runs/40711359655

HA CI: https://github.com/Tmatz27/Home-assistant-photography-events/actions/runs/40711986071

Later documentation/evidence commits do not change the tested code. Use the
candidate SHAs, never an unreviewed newer main, as future release targets.

Core evidence: `docs/evidence/batch2a-deployment/`. HA evidence:
`docs/v17b/evidence/batch2a-deployment/`. Each has `candidate-pair.json` and
committed evidence digests. Full changed-file scope is the diff between each
starting main and candidate freeze.

Core: 615 real PostgreSQL 18/PostGIS 3.6 tests passed with no skips/failures;
all 611 accepted R1–R3 identities retained. Portable 257 passed/358 expected
DB skips; Ruff/compile and M1 parity (18,000 comparisons, zero mismatches)
passed. Fresh image-only runtime, existing-volume/password/role preservation,
restart/restore and explicit 0009→0010 comparison of 34
application tables/46 rows
passed. Nonempty lease/checkpoint/backoff survived. Actual runtime settings
confirm historical collection true, scope JSON {} and all 81 inventory keys.
Runtime source, migrations and deployment configuration are unchanged from the
accepted Batch 2A freeze; only verification/tools/docs were added.

HA: 697 portable-discovery tests (577 passed, 120 expected HA skips), 158 JS
tests, HACS, pyflakes, build/version checks, import-boundary audit and both real
HA matrix versions passed. Each matrix runs the v17b lifecycle suite plus all
HA contract modules; those overlap, so do not add their counts as unique tests.
The new route job reproduces five accepted Core ASGI responses and four bearer
rejections using explicitly synthetic upstream test data; no live DB/lifespan.

Focus independent review on:

1. Explicit wire schemas 0008/0009/0010 at BOTH core_client and projection/cache
   guards. Future 0011, bad API/engine versions, malformed rows, unknown product
   identities and debug/shadow payloads remain rejected. This is not a schema
   range or generic database-version acceptance.
2. Separate destination/source/definition pinning, withheld coordinates/prose,
   strict booleans/enums/times, source/error redaction, bearer/origin binding,
   redirects/size limits, cache namespace/clocks and no authority on reconnect.
   No HA provider, intelligence, event, notification or opportunity publication
   path was added. The card diff is only its synchronized version constant.
3. Core Compose passes CORE_COLLECTION_SCOPE_JSON and CORE_SOURCE_HISTORY=true
   by default; no path/password/network/health/persistence/role change. Review
   the CI-only upgrade guard, exact pre/post snapshots and sentinel cleanup,
   alongside fresh initialization and existing-volume recreation evidence.
4. The development HA release argument policy uses --prerelease --latest=false.
   Core still publishes only from an explicitly published GitHub Release after
   validation, builds on GitHub, and verifies anonymous GHCR pulls afterward.
   No tag, release or image is published during this preparation.
5. Deployment order: verified backups, approved HA beta first (still accepts
   Core 0009), approved Core prerelease/public-pull gate, then existing Unraid
   Compose Manager Pull & Up and operator verification. No local checkout/build,
   auto-update, database reset or password rotation. 0010 is forward-only;
   rollback needs the matching pre-upgrade database backup and image/config.

Core instructions: `docs/BATCH_2A_DEPLOYMENT_CANDIDATE.md`. HA instructions:
`docs/v17b/BATCH_2A_DEPLOYMENT.md`. NPS credentials, full historical backfill,
installed collection/reachability and full ingestion acceptance remain pending.
Do not confuse disposable test success with installed Unraid verification.

Return PASS, PASS WITH REQUIRED FIXES, or FAIL with severity, exact lines and
reproduction. Do not publish, push release tags, run release workflows, deploy,
connect to Unraid or start Batch 2B during review. Stop for the user's explicit
publication/deployment approval after independent review. All 81 source entries
and continued historical collection remain the committed scope for Batch 2B.
