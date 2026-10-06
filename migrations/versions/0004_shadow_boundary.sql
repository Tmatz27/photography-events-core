ALTER TABLE pattern_generation_runs
 ADD COLUMN status TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('running','published','superseded','failed')),
 ADD COLUMN started_at TIMESTAMPTZ,
 ADD COLUMN completed_at TIMESTAMPTZ,
 ADD COLUMN input_fingerprint TEXT CHECK(input_fingerprint IS NULL OR length(input_fingerprint)=64),
 ADD COLUMN error_code TEXT CHECK(error_code IS NULL OR error_code IN ('shadow_failed','shadow_cancelled'));
UPDATE pattern_generation_runs SET started_at=calculated_at,completed_at=calculated_at;
ALTER TABLE pattern_generation_runs ALTER COLUMN started_at SET NOT NULL;
ALTER TABLE pattern_generation_runs ADD CONSTRAINT ck_pattern_run_completion
 CHECK((status='running')=(completed_at IS NULL));
CREATE INDEX ix_pattern_run_status ON pattern_generation_runs(status,started_at);

