-- Typed source-neutral lifecycle fences. Evidence timestamps are unchanged.
ALTER TABLE source_poll_state ADD COLUMN last_applied_poll_started_at TIMESTAMPTZ;
UPDATE source_poll_state p SET last_applied_poll_started_at=(SELECT max(started_at) FROM source_runs WHERE source_id=p.source_id);
ALTER TABLE raw_observations ADD COLUMN state_poll_started_at TIMESTAMPTZ;
ALTER TABLE raw_observations ADD COLUMN retired_at TIMESTAMPTZ;
ALTER TABLE raw_observations ADD COLUMN retirement_reason TEXT;
ALTER TABLE raw_observations ADD COLUMN retirement_provider_updated_at TIMESTAMPTZ;
ALTER TABLE raw_observations ADD COLUMN retired_source_run_id BIGINT REFERENCES source_runs(id);
ALTER TABLE raw_observations ADD COLUMN privacy_source_run_id BIGINT REFERENCES source_runs(id);
UPDATE raw_observations r SET state_poll_started_at=COALESCE((SELECT started_at FROM source_runs WHERE id=r.source_run_id),r.fetched_at);
UPDATE raw_observations r SET retired_at=(SELECT max(superseded_at) FROM normalized_observations WHERE raw_observation_id=r.id),
 retirement_reason='legacy_retired' WHERE EXISTS(SELECT 1 FROM normalized_observations WHERE raw_observation_id=r.id)
 AND NOT EXISTS(SELECT 1 FROM normalized_observations WHERE raw_observation_id=r.id AND superseded_at IS NULL);
ALTER TABLE source_runs ADD COLUMN reinstated INTEGER NOT NULL DEFAULT 0 CHECK(reinstated>=0);
