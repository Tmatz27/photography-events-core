# Milestone 1 schema correction: revision 0002

Revision 0001 is unchanged; its complete column inventory remains in
[SCHEMA_MILESTONE_1.md](SCHEMA_MILESTONE_1.md). Apply 0002 after 0001. The Python
migration first discovers and drops the old normalized-assertion uniqueness
constraint (PostgreSQL may truncate its generated name); the exact SQL below
then applies transactionally. See [the migration wrapper](../migrations/versions/0002_generations.py).

## Current inventory

There are 19 application tables, plus Alembic metadata and PostGIS relations.
The existing `source_health_current` view remains collection-health only.

| Relation | Current purpose / change |
|---|---|
| sources | Stable source registry; requires_stable_ids policy flag |
| source_roles | Existing source-role mapping |
| source_runs | Append attempts; canonical content hash and provider-native fixture context |
| source_backoff | Persist scheduler restart state |
| raw_observations | Current provider record by source/external ID; content hash and monotonic automated protection |
| normalized_observations | Immutable assertion content except protection increases; superseded_at distinguishes current; source-run/hash provenance |
| locations | Existing curated analysis/public geometry |
| phenomenon_locations | Existing phenomenon/site association |
| route_baselines | Existing route table, unused by a live routing collector |
| assessment_runs | Generation status, watermark, fingerprint, rule/engine provenance, expected item count, failure code |
| opportunities | Stable occurrence registry only: id, occurrence_key, phenomenon_key, location_id |
| opportunity_revisions | Typed material changes; composite generation-item FK, explicit legacy_unscoped status |
| assessment_current | Singleton id=1; nullable current generation FK |
| assessment_opportunities | Typed decision plus versioned/checksummed product JSON; composite generation/item PK |
| assessment_sources | Required/consulted source role and exact run; composite run/source FK prevents mismatching provenance |
| opportunity_observation_evidence | Generation/item/assertion association with strict FKs |
| opportunity_context_evidence | Generation/item/source-run association with strict FKs |
| legacy_observation_evidence | Original 0001 associations preserved verbatim; not claimed as verified generation evidence |
| legacy_context_evidence | Original 0001 context associations preserved verbatim |

Generation item columns copy 0001's typed opportunity decision/check model,
with occurrence identity resolved from the stable registry. Product JSON is
API version 1 data, validated with Pydantic and compared with typed decisions.
Its stored PostgreSQL canonical JSONB SHA-256 catches accidental changes even
to valid-looking fields not duplicated in typed columns. This checksum is an
integrity check, not protection against a privileged writer changing both data
and checksum. Application publication owns these writes.

Current assertions are unique per raw record + subject type + subject key,
using a partial index where superseded_at IS NULL. Generation and evidence
indexes support current membership, provenance joins and history. Dropped
decision columns automatically remove their old registry indexes; explicit
replacement indexes live on assessment_opportunities. The existing analysis
geometry GiST index remains. Protection requires public_geometry IS NULL for
sensitive assertions. No generic polymorphic evidence relation is introduced.

## Existing-data policy and rollback

Migration retains stable occurrence IDs/keys, raw provider identities/payloads,
typed decisions, old revisions, and both original evidence tables. It marks old
decisions incomplete with legacy_provenance_unverified because 0001 did not
retain enough provenance to prove a generation. Old revisions remain
legacy_unscoped; no historical generation links are invented. The newest
legacy watermark is selected as a held readable snapshot until a newer
successful evaluation uses verified inputs. Source collection success without
stored safety context cannot make that new generation complete.

For the installed fixture source only, a species/timestamp mismatch between
raw and normalized data supersedes the stale assertion. A matching current
assertion may restore internal analysis geometry from the restricted raw
point; public geometry is withheld. No raw private point enters an API DTO.

**0002 is forward-only.** Its histories cannot be collapsed into 0001 without
loss. Take and verify a pre-upgrade backup; rollback means restoring it into a
new database and using the pre-upgrade image. The original disposable 0001
downgrade/base/upgrade test remains; 0002 upgrade, repeat upgrade and actual
script backup/restore pass in CI. See R20 in the
[correction review](../IMPLEMENTATION_REVIEW_MILESTONE_1.md#independent-review-correction-pass).

## Exact SQL supplement

```sql
-- Preserve ambiguous first-pass evidence verbatim; do not invent historical provenance.
ALTER TABLE opportunity_observation_evidence RENAME TO legacy_observation_evidence;
ALTER TABLE opportunity_context_evidence RENAME TO legacy_context_evidence;

ALTER TABLE assessment_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'superseded'
 CHECK (status IN ('published','superseded','failed'));
ALTER TABLE assessment_runs ADD COLUMN input_fingerprint TEXT
 CHECK (input_fingerprint IS NULL OR length(input_fingerprint)=64);
ALTER TABLE assessment_runs ADD COLUMN engine_version TEXT NOT NULL DEFAULT '0.1.0-dev';
ALTER TABLE assessment_runs ADD COLUMN definition_hash TEXT;
ALTER TABLE assessment_runs ADD COLUMN error_code TEXT;
ALTER TABLE assessment_runs ADD COLUMN expected_items INTEGER NOT NULL DEFAULT 0 CHECK (expected_items>=0);
CREATE INDEX ix_assessment_watermark ON assessment_runs(data_as_of DESC);
CREATE INDEX ix_assessment_conflict ON assessment_runs(data_as_of) WHERE error_code='input_conflict';

CREATE TABLE assessment_current (
 id SMALLINT PRIMARY KEY CHECK(id=1),
 assessment_run_id BIGINT UNIQUE REFERENCES assessment_runs(id)
);
INSERT INTO assessment_current(id) VALUES(1);

-- Copy the existing typed decision model, including all CHECK constraints.
-- Identity fields are resolved from the stable registry; decisions never move.
CREATE TABLE assessment_opportunities (LIKE opportunities INCLUDING CONSTRAINTS);
ALTER TABLE assessment_opportunities RENAME COLUMN id TO opportunity_id;
ALTER TABLE assessment_opportunities DROP COLUMN occurrence_key;
ALTER TABLE assessment_opportunities DROP COLUMN phenomenon_key;
ALTER TABLE assessment_opportunities ADD COLUMN product_version INTEGER NOT NULL DEFAULT 1 CHECK(product_version=1);
ALTER TABLE assessment_opportunities ADD PRIMARY KEY(assessment_run_id,opportunity_id);
ALTER TABLE assessment_opportunities ADD FOREIGN KEY(assessment_run_id) REFERENCES assessment_runs(id);
ALTER TABLE assessment_opportunities ADD FOREIGN KEY(opportunity_id) REFERENCES opportunities(id);
ALTER TABLE assessment_opportunities ADD FOREIGN KEY(location_id) REFERENCES locations(id);
CREATE INDEX ix_generation_opportunity ON assessment_opportunities(opportunity_id,assessment_run_id);
CREATE INDEX ix_generation_location ON assessment_opportunities(location_id);
CREATE INDEX ix_generation_presentation ON assessment_opportunities(assessment_run_id,presentation,ends_at);

INSERT INTO assessment_opportunities(opportunity_id,assessment_run_id,location_id,starts_at,ends_at,category,
 presentation,eligibility,significance,confidence,urgency,evidence_state,access_state,safety_state,condition_state,
 drive_minutes,drive_basis,reason,awaiting,definition_key,definition_version,definition_hash,engine_version,
 data_as_of,valid_until,product)
 SELECT id,assessment_run_id,location_id,starts_at,ends_at,category,
 presentation,eligibility,significance,confidence,urgency,evidence_state,access_state,safety_state,condition_state,
 drive_minutes,drive_basis,reason,awaiting,definition_key,definition_version,definition_hash,engine_version,
 data_as_of,valid_until,product FROM opportunities;

ALTER TABLE assessment_opportunities ADD COLUMN product_sha256 TEXT;
UPDATE assessment_opportunities SET product_sha256=encode(sha256(convert_to(product::text,'UTF8')),'hex');
ALTER TABLE assessment_opportunities ALTER COLUMN product_sha256 SET NOT NULL;
ALTER TABLE assessment_opportunities ADD CHECK(length(product_sha256)=64);

UPDATE assessment_runs a SET expected_items=(SELECT count(*) FROM assessment_opportunities p WHERE p.assessment_run_id=a.id),
 state='incomplete',error_code='legacy_provenance_unverified';
UPDATE assessment_current SET assessment_run_id=(SELECT id FROM assessment_runs ORDER BY data_as_of DESC,generated_at DESC,id DESC LIMIT 1);
UPDATE assessment_runs SET status='published' WHERE id=(SELECT assessment_run_id FROM assessment_current);

-- Old revisions stay unscoped rather than claiming the wrong historical evidence.
ALTER TABLE opportunity_revisions ADD COLUMN assessment_run_id BIGINT;
ALTER TABLE opportunity_revisions ADD COLUMN provenance_status TEXT NOT NULL DEFAULT 'legacy_unscoped'
 CHECK(provenance_status IN ('legacy_unscoped','generation'));
ALTER TABLE opportunity_revisions ADD CHECK
 ((provenance_status='generation' AND assessment_run_id IS NOT NULL) OR
  (provenance_status='legacy_unscoped' AND assessment_run_id IS NULL));
ALTER TABLE opportunity_revisions ADD FOREIGN KEY(assessment_run_id,opportunity_id)
 REFERENCES assessment_opportunities(assessment_run_id,opportunity_id);
CREATE INDEX ix_revision_generation ON opportunity_revisions(assessment_run_id,opportunity_id);

ALTER TABLE opportunities DROP COLUMN assessment_run_id,
 DROP COLUMN starts_at,DROP COLUMN ends_at,DROP COLUMN category,DROP COLUMN presentation,
 DROP COLUMN eligibility,DROP COLUMN significance,DROP COLUMN confidence,DROP COLUMN urgency,
 DROP COLUMN evidence_state,DROP COLUMN access_state,DROP COLUMN safety_state,DROP COLUMN condition_state,
 DROP COLUMN drive_minutes,DROP COLUMN drive_basis,DROP COLUMN reason,DROP COLUMN awaiting,
 DROP COLUMN definition_key,DROP COLUMN definition_version,DROP COLUMN definition_hash,DROP COLUMN engine_version,
 DROP COLUMN data_as_of,DROP COLUMN valid_until,DROP COLUMN product;

ALTER TABLE sources ADD COLUMN requires_stable_ids BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE source_runs ADD COLUMN content_sha256 TEXT CHECK(content_sha256 IS NULL OR length(content_sha256)=64);
-- Provider-native fixture context (NWS alerts) is data, never executable policy.
ALTER TABLE source_runs ADD COLUMN context_payload JSONB;
ALTER TABLE source_runs ADD UNIQUE(id,source_id);
CREATE TABLE assessment_sources (
 assessment_run_id BIGINT NOT NULL REFERENCES assessment_runs(id),
 source_id BIGINT NOT NULL REFERENCES sources(id),
 source_run_id BIGINT,
 role TEXT NOT NULL CHECK(role IN ('DISCOVERY','PLANNING','WATCH_SIGNAL','CONFIRMATION','CORROBORATION','CONDITION','ACCESS','SAFETY')),
 required BOOLEAN NOT NULL,
 consulted BOOLEAN NOT NULL,
 PRIMARY KEY(assessment_run_id,source_id,role),
 FOREIGN KEY(source_run_id,source_id) REFERENCES source_runs(id,source_id)
);
CREATE INDEX ix_assessment_source_run ON assessment_sources(source_run_id);
CREATE INDEX ix_assessment_source_source ON assessment_sources(source_id);

ALTER TABLE raw_observations ADD COLUMN content_sha256 TEXT CHECK(content_sha256 IS NULL OR length(content_sha256)=64);
ALTER TABLE raw_observations ADD COLUMN sensitive BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE raw_observations r SET sensitive=EXISTS(SELECT 1 FROM normalized_observations n WHERE n.raw_observation_id=r.id AND n.sensitive);
ALTER TABLE normalized_observations ADD COLUMN superseded_at TIMESTAMPTZ;
ALTER TABLE normalized_observations ADD COLUMN behavior TEXT;
ALTER TABLE normalized_observations ADD COLUMN source_run_id BIGINT REFERENCES source_runs(id);
ALTER TABLE normalized_observations ADD COLUMN content_sha256 TEXT;
UPDATE normalized_observations n SET source_run_id=r.source_run_id FROM raw_observations r WHERE r.id=n.raw_observation_id;
-- Reconcile only the installed fixture policy. Old mismatched assertions stay
-- available to legacy evidence but cannot participate in new assessments.
UPDATE normalized_observations n SET superseded_at=r.fetched_at
 FROM raw_observations r JOIN sources s ON s.id=r.source_id
 WHERE n.raw_observation_id=r.id AND s.key='fixture_observations' AND n.subject_type='species'
 AND (n.subject_key IS DISTINCT FROM r.raw_payload->>'scientific_name' OR n.observed_at IS DISTINCT FROM r.observed_at);
-- Private observations lost usable analysis geometry in the first pass.
-- Restore the restricted internal point where stored raw provenance supports it.
UPDATE normalized_observations n SET analysis_geometry=r.exact_geometry,public_geometry=NULL,
 sensitive=(r.sensitive OR n.sensitive),precision_class='withheld'
 FROM raw_observations r JOIN sources s ON s.id=r.source_id
 WHERE n.raw_observation_id=r.id AND s.key='fixture_observations' AND n.subject_type='species'
 AND n.superseded_at IS NULL AND r.exact_geometry IS NOT NULL;
CREATE UNIQUE INDEX ux_normalized_current ON normalized_observations(raw_observation_id,subject_type,subject_key)
 WHERE superseded_at IS NULL;
CREATE INDEX ix_normalized_current_time ON normalized_observations(observed_at,valid_until) WHERE superseded_at IS NULL;
CREATE INDEX ix_normalized_source_run ON normalized_observations(source_run_id);
ALTER TABLE normalized_observations ADD CHECK(NOT sensitive OR public_geometry IS NULL);

CREATE TABLE opportunity_observation_evidence (
 assessment_run_id BIGINT NOT NULL,
 opportunity_id BIGINT NOT NULL,
 normalized_observation_id BIGINT NOT NULL REFERENCES normalized_observations(id),
 disposition TEXT NOT NULL CHECK(disposition IN ('SUPPORTING','CONTRADICTORY','NEUTRAL')),
 PRIMARY KEY(assessment_run_id,opportunity_id,normalized_observation_id),
 FOREIGN KEY(assessment_run_id,opportunity_id) REFERENCES assessment_opportunities(assessment_run_id,opportunity_id)
);
CREATE INDEX ix_generation_evidence_observation ON opportunity_observation_evidence(normalized_observation_id);
CREATE TABLE opportunity_context_evidence (
 assessment_run_id BIGINT NOT NULL,
 opportunity_id BIGINT NOT NULL,
 source_run_id BIGINT NOT NULL REFERENCES source_runs(id),
 disposition TEXT NOT NULL CHECK(disposition IN ('SUPPORTING','CONTRADICTORY','NEUTRAL')),
 PRIMARY KEY(assessment_run_id,opportunity_id,source_run_id),
 FOREIGN KEY(assessment_run_id,opportunity_id) REFERENCES assessment_opportunities(assessment_run_id,opportunity_id)
);
CREATE INDEX ix_generation_evidence_context ON opportunity_context_evidence(source_run_id);
```

