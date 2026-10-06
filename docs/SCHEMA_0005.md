# Schema 0005 — final independent corrections

Append-only after unchanged 0001–0004. There are 32 application tables after
this revision: 31 existing plus pattern_coherence_rejections. The transaction-
local origin_mismatches scratch table is dropped on commit and is not an
application table. No external source family or executable policy blob is added.

| Change | Inventory |
|---|---|
| normalized_observations.origin_identity_status | Required controlled status: provider_identity / explicit_verified / explicit_unverified / origin_identity_mismatch; default provider_identity |
| ix_pattern_current_observed | B-tree observed_at over current species assertions; supports policy-derived SQL time range |
| Legacy canonical behavior | Exact trimmed case-insensitive bugling→rut insert, preserving existing behavior and evidence rows; conflict-safe |
| Existing explicit identity links | Revalidate against current origin-provider assertions by exact taxon and ±1 hour; rehome mismatches to provider-qualified IDs, superseding links without rewriting historical cluster memberships |
| pattern_episode_snapshots.transition_code check | Existing values retained; coherence_rejected added |
| pattern_coherence_rejections | Per-generation/policy/candidate audit row; all columns, checks and PK/FK reproduced below |

Each rejected candidate stores policy key/version/hash, observation/report
counts, primary epsilon, candidate enclosing radius/diameter, configured maximum,
optional fallback epsilon, whether attempted, outcome, recovered cluster count
and sensitivity. It stores no point geometry. Private diagnostic metrics are
withheld by the debug DTO, including immediate protection raises and cumulative
protected episode state. Unpublished run diagnostics are not exposed as current.

Fresh/head and seeded 0001→0002→0003→0004→0005 tests preserve the legacy API,
private geometry, report history and existing shadow hashes/timestamps. The 0004
seed includes bugling and contradictory subject/time mirror claims to exercise
the data repairs. Downgrade is forward-only; restore a verified pre-upgrade backup
to a fresh compatible DB. Exact SQL inventory follows.

```sql
ALTER TABLE normalized_observations ADD COLUMN origin_identity_status TEXT NOT NULL DEFAULT 'provider_identity'
 CHECK(origin_identity_status IN ('provider_identity','explicit_verified','explicit_unverified','origin_identity_mismatch'));
-- Revalidate pre-existing definitive claims against current canonical assertions.
-- This is exact subject/time consistency, never a proximity dedupe.
UPDATE normalized_observations n SET origin_identity_status='explicit_unverified'
 FROM observation_report_group_members m
 WHERE m.normalized_observation_id=n.id AND m.superseded_at IS NULL AND m.link_basis='explicit_origin_id';
CREATE TEMP TABLE origin_mismatches ON COMMIT DROP AS
 SELECT m.id AS membership_id,n.id AS nid,s.key AS namespace,
 COALESCE(NULLIF(r.raw_payload->>'report_external_id',''),r.external_id,'legacy-raw-'||r.id) AS origin,
 GREATEST(CURRENT_TIMESTAMP,m.created_at) AS corrected_at
 FROM observation_report_group_members m JOIN normalized_observations n ON n.id=m.normalized_observation_id
 JOIN raw_observations r ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id
 JOIN observation_report_groups g ON g.id=m.report_group_id
 WHERE m.superseded_at IS NULL AND n.superseded_at IS NULL AND m.link_basis='explicit_origin_id'
 AND EXISTS(SELECT 1 FROM observation_report_group_members cm JOIN normalized_observations cn ON cn.id=cm.normalized_observation_id
 JOIN raw_observations cr ON cr.id=cn.raw_observation_id JOIN sources cs ON cs.id=cr.source_id
 WHERE cm.report_group_id=m.report_group_id AND cm.superseded_at IS NULL AND cn.superseded_at IS NULL
 AND cs.key=g.origin_namespace)
 AND NOT EXISTS(SELECT 1 FROM observation_report_group_members cm JOIN normalized_observations cn ON cn.id=cm.normalized_observation_id
 JOIN raw_observations cr ON cr.id=cn.raw_observation_id JOIN sources cs ON cs.id=cr.source_id
 WHERE cm.report_group_id=m.report_group_id AND cm.superseded_at IS NULL AND cn.superseded_at IS NULL
 AND cs.key=g.origin_namespace AND lower(cn.subject_key)=lower(n.subject_key)
 AND abs(extract(epoch FROM cn.observed_at-n.observed_at))<=3600);
INSERT INTO observation_report_groups(origin_namespace,origin_external_id,created_at)
 SELECT namespace,origin,min(corrected_at) FROM origin_mismatches GROUP BY namespace,origin
 ON CONFLICT(origin_namespace,origin_external_id) DO NOTHING;
UPDATE observation_report_group_members m SET superseded_at=x.corrected_at FROM origin_mismatches x WHERE m.id=x.membership_id;
INSERT INTO observation_report_group_members(report_group_id,normalized_observation_id,link_basis,created_at)
 SELECT g.id,x.nid,'provider_identity',x.corrected_at FROM origin_mismatches x JOIN observation_report_groups g
 ON g.origin_namespace=x.namespace AND g.origin_external_id=x.origin;
UPDATE normalized_observations n SET origin_identity_status='origin_identity_mismatch' FROM origin_mismatches x WHERE n.id=x.nid;
UPDATE normalized_observations n SET origin_identity_status='explicit_verified'
 FROM observation_report_group_members m JOIN observation_report_groups g ON g.id=m.report_group_id
 WHERE m.normalized_observation_id=n.id AND m.superseded_at IS NULL AND m.link_basis='explicit_origin_id'
 AND n.superseded_at IS NULL AND EXISTS(SELECT 1 FROM observation_report_group_members cm
 JOIN normalized_observations cn ON cn.id=cm.normalized_observation_id JOIN raw_observations cr ON cr.id=cn.raw_observation_id
 JOIN sources cs ON cs.id=cr.source_id WHERE cm.report_group_id=m.report_group_id AND cm.superseded_at IS NULL
 AND cn.superseded_at IS NULL AND cs.key=g.origin_namespace
 AND lower(cn.subject_key)=lower(n.subject_key) AND abs(extract(epoch FROM cn.observed_at-n.observed_at))<=3600);
CREATE INDEX ix_pattern_current_observed ON normalized_observations(observed_at)
 WHERE superseded_at IS NULL AND subject_type='species';
INSERT INTO normalized_observation_behaviors(normalized_observation_id,behavior_code,created_at)
 SELECT id,'rut',observed_at FROM normalized_observations WHERE lower(trim(behavior))='bugling'
 ON CONFLICT(normalized_observation_id,behavior_code) DO NOTHING;
ALTER TABLE pattern_episode_snapshots DROP CONSTRAINT pattern_episode_snapshots_transition_code_check;
ALTER TABLE pattern_episode_snapshots ADD CONSTRAINT pattern_episode_snapshots_transition_code_check
 CHECK(transition_code IN ('created','continued','split','merged','expired','policy_changed','unsupported','merge_ambiguous','coherence_rejected'));
CREATE TABLE pattern_coherence_rejections (
 assessment_run_id BIGINT NOT NULL REFERENCES pattern_generation_runs(assessment_run_id),
 phenomenon_key TEXT NOT NULL,
 candidate_key TEXT NOT NULL CHECK(length(candidate_key)=64),
 policy_version TEXT NOT NULL,
 policy_hash TEXT NOT NULL CHECK(length(policy_hash)=64),
 candidate_observation_count INTEGER NOT NULL CHECK(candidate_observation_count>0),
 independent_report_count INTEGER NOT NULL CHECK(independent_report_count>0),
 primary_eps_meters DOUBLE PRECISION NOT NULL CHECK(primary_eps_meters>0 AND primary_eps_meters<'Infinity'::float8),
 candidate_radius_meters DOUBLE PRECISION NOT NULL CHECK(candidate_radius_meters>=0 AND candidate_radius_meters<'Infinity'::float8),
 candidate_diameter_meters DOUBLE PRECISION NOT NULL CHECK(candidate_diameter_meters>=0 AND candidate_diameter_meters<'Infinity'::float8),
 maximum_diameter_meters DOUBLE PRECISION NOT NULL CHECK(maximum_diameter_meters>0 AND maximum_diameter_meters<'Infinity'::float8),
 fallback_eps_meters DOUBLE PRECISION CHECK(fallback_eps_meters>0 AND fallback_eps_meters<primary_eps_meters),
 fallback_attempted BOOLEAN NOT NULL,
 fallback_result TEXT NOT NULL CHECK(fallback_result IN ('not_configured','no_qualifying_core','recovered')),
 recovered_cluster_count INTEGER NOT NULL CHECK(recovered_cluster_count>=0),
 contains_sensitive_evidence BOOLEAN NOT NULL,
 PRIMARY KEY(assessment_run_id,phenomenon_key,candidate_key),
 CHECK(fallback_attempted=(fallback_eps_meters IS NOT NULL)),
 CHECK((fallback_result='recovered')=(recovered_cluster_count>0))
);
```
