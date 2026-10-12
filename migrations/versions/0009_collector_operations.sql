-- Short durable leases; no connection or M1 publication lock held over HTTP.
ALTER TABLE source_poll_state ADD COLUMN lease_token UUID;
ALTER TABLE source_poll_state ADD COLUMN lease_until TIMESTAMPTZ;
ALTER TABLE source_poll_state ADD COLUMN checkpoint JSONB NOT NULL DEFAULT '{}'
 CHECK(jsonb_typeof(checkpoint)='object');
ALTER TABLE source_poll_state ADD CHECK ((lease_token IS NULL)=(lease_until IS NULL));
-- Explicit CAP references remain version barriers even after bulk payload retention.
CREATE TABLE source_reference_barriers (
 source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 external_id TEXT NOT NULL,
 provider_updated_at TIMESTAMPTZ NOT NULL,
 source_run_id BIGINT NOT NULL REFERENCES source_runs(id),
 PRIMARY KEY(source_id,external_id)
);
INSERT INTO source_reference_barriers(source_id,external_id,provider_updated_at,source_run_id)
 SELECT DISTINCT ON (r.source_id,p->>'identifier')
 r.source_id,p->>'identifier',r.provider_updated_at,r.source_run_id
 FROM raw_observations r JOIN sources s ON s.id=r.source_id
 CROSS JOIN LATERAL jsonb_array_elements(CASE
 WHEN jsonb_typeof(r.raw_payload->'properties'->'references')='array'
 THEN r.raw_payload->'properties'->'references' ELSE '[]'::jsonb END) p
 WHERE s.key='nws_live_context' AND r.raw_payload->'properties'->>'messageType' IN ('Cancel','Update')
 AND r.provider_updated_at<=r.fetched_at+INTERVAL '1 hour'
 AND r.source_run_id IS NOT NULL AND p->>'identifier' IS NOT NULL
 ORDER BY r.source_id,p->>'identifier',r.provider_updated_at DESC,r.id DESC;
CREATE INDEX source_poll_lease_until ON source_poll_state(lease_until) WHERE lease_token IS NOT NULL;
