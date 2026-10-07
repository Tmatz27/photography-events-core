-- H3 EXPLAIN receipts: qualified lookups otherwise revisit every retained
-- current assertion for each key. These exact expressions match adapter IDs,
-- including explicit report aliases and legacy fallback IDs.
CREATE INDEX ix_raw_local_report_identity ON raw_observations
 (source_id,(COALESCE(raw_payload->>'report_external_id',external_id,'legacy-raw-'||id::text)));
-- Invalid claims keep their durable target even after independent rehoming.
CREATE INDEX ix_raw_explicit_origin ON raw_observations
 ((raw_payload->>'origin_namespace'),(raw_payload->>'origin_external_id'))
 WHERE raw_payload ? 'origin_namespace' AND raw_payload ? 'origin_external_id';
-- Retirement touches superseded versions of selected provider records only.
CREATE INDEX ix_normalized_superseded_raw ON normalized_observations(raw_observation_id,id)
 WHERE superseded_at IS NOT NULL;
