# Schema 0006 — bounded identity dependency lookups

Append-only after unchanged migrations 0001–0005. The 32 application tables and
all fields, constraints, biological policies and historical evidence remain
unchanged. The migration adds three B-tree indexes justified by real PostGIS
EXPLAIN ANALYZE receipts in the H3 implementation review.

| Index | Purpose |
|---|---|
| ix_raw_local_report_identity | Source-qualified canonical/stable report ID lookup, including explicit report aliases and legacy fallback IDs |
| ix_raw_explicit_origin | Qualified durable origin claims, including rejected mirrors currently rehomed into independent groups; partial over bodies carrying both claim keys |
| ix_normalized_superseded_raw | Superseded normalized versions belonging to selected provider records; avoids global membership retirement scans |

The existing ux_normalized_current index resolves current species assertions
for each selected raw record. Existing group/current-membership indexes resolve
previously established explicit relationships after ordinary payload pruning.
Existing policy-window indexes admit the primary active set.

The migration does not delete or supersede observations, prune evidence, backfill
identity, add a watermark, or create a new provider contract. Index build cost and
normal per-write maintenance remain. Upgrade startup uses transactional Alembic;
verify a backup before an operator upgrade. This revision is forward-only: restore
a verified pre-upgrade backup to a new database with the matching application
image if rollback is required.

Exact SQL:

```sql
CREATE INDEX ix_raw_local_report_identity ON raw_observations
 (source_id,(COALESCE(raw_payload->>'report_external_id',external_id,'legacy-raw-'||id::text)));
CREATE INDEX ix_raw_explicit_origin ON raw_observations
 ((raw_payload->>'origin_namespace'),(raw_payload->>'origin_external_id'))
 WHERE raw_payload ? 'origin_namespace' AND raw_payload ? 'origin_external_id';
CREATE INDEX ix_normalized_superseded_raw ON normalized_observations(raw_observation_id,id)
 WHERE superseded_at IS NOT NULL;
```
