-- DATE is not an invented observation instant. Existing timestamp rows remain unchanged.
ALTER TABLE normalized_observations ALTER COLUMN observed_at DROP NOT NULL;
ALTER TABLE normalized_observations ADD COLUMN observed_date DATE;
ALTER TABLE normalized_observations ADD COLUMN observed_time_zone TEXT;
ALTER TABLE normalized_observations ADD COLUMN time_precision TEXT NOT NULL DEFAULT 'timestamp'
 CHECK(time_precision IN ('timestamp','date','model'));
ALTER TABLE normalized_observations ADD CHECK (
 (time_precision='date' AND observed_at IS NULL AND observed_date IS NOT NULL) OR
 (time_precision IN ('timestamp','model') AND observed_at IS NOT NULL));
ALTER TABLE normalized_observations ADD COLUMN provider_updated_at TIMESTAMPTZ;
ALTER TABLE normalized_observations ADD COLUMN source_metadata JSONB NOT NULL DEFAULT '{}'
 CHECK(jsonb_typeof(source_metadata)='object');
ALTER TABLE normalized_observations ADD COLUMN spatial_basis TEXT NOT NULL DEFAULT 'unknown'
 CHECK(spatial_basis IN ('unknown','open_point','obscured_cell','private_unavailable','area_only'));
ALTER TABLE normalized_observations ADD COLUMN analysis_area geometry(Geometry,4326)
 CHECK(analysis_area IS NULL OR (GeometryType(analysis_area) IN ('POLYGON','MULTIPOLYGON') AND ST_IsValid(analysis_area)));
ALTER TABLE normalized_observations DROP CONSTRAINT normalized_observations_subject_type_check;
ALTER TABLE normalized_observations ADD CHECK(subject_type IN ('species','behavior','safety','condition'));
-- Preserve legacy exact_geometry semantics. Provider-returned public geometry
-- has its own name/basis and is never serialized as a product destination.
ALTER TABLE raw_observations ADD COLUMN provider_geometry geometry(Geometry,4326);
ALTER TABLE raw_observations ADD COLUMN spatial_basis TEXT NOT NULL DEFAULT 'unknown'
 CHECK(spatial_basis IN ('unknown','open_point','obscured_cell','private_unavailable','area_only'));
ALTER TABLE raw_observations ADD COLUMN provider_updated_at TIMESTAMPTZ;
ALTER TABLE source_runs ADD COLUMN contract_version TEXT;
ALTER TABLE source_runs ADD COLUMN parser_version TEXT;
ALTER TABLE source_runs ADD COLUMN requests INTEGER NOT NULL DEFAULT 0 CHECK(requests>=0);
ALTER TABLE source_runs ADD COLUMN bytes_received BIGINT NOT NULL DEFAULT 0 CHECK(bytes_received>=0);
ALTER TABLE source_runs ADD COLUMN unique_records INTEGER NOT NULL DEFAULT 0 CHECK(unique_records>=0);
ALTER TABLE source_runs ADD COLUMN corrections INTEGER NOT NULL DEFAULT 0 CHECK(corrections>=0);
ALTER TABLE source_runs ADD COLUMN duplicates INTEGER NOT NULL DEFAULT 0 CHECK(duplicates>=0);
ALTER TABLE source_runs ADD COLUMN obscured_records INTEGER NOT NULL DEFAULT 0 CHECK(obscured_records>=0);
ALTER TABLE source_runs ADD COLUMN private_records INTEGER NOT NULL DEFAULT 0 CHECK(private_records>=0);
ALTER TABLE source_runs ADD COLUMN rate_limit_count INTEGER NOT NULL DEFAULT 0 CHECK(rate_limit_count>=0);
ALTER TABLE source_runs ADD COLUMN parser_error_counts JSONB NOT NULL DEFAULT '{}'
 CHECK(jsonb_typeof(parser_error_counts)='object');
ALTER TABLE source_runs ADD COLUMN incomplete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE pattern_generation_runs ADD COLUMN identity_rejected_count INTEGER NOT NULL DEFAULT 0 CHECK(identity_rejected_count>=0);
CREATE TABLE source_poll_state (
 source_id BIGINT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
 cursor_updated_at TIMESTAMPTZ,
 refresh_after_id BIGINT NOT NULL DEFAULT 0 CHECK(refresh_after_id>=0),
 quota_day DATE,
 requests_today INTEGER NOT NULL DEFAULT 0 CHECK(requests_today>=0),
 last_request_at TIMESTAMPTZ
);
