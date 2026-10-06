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
