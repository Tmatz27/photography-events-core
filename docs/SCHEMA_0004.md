# Schema 0004 — independent shadow lifecycle

This forward-only migration follows unchanged 0001, 0002 and 0003. It creates no
new tables and does not rewrite identity, behavior, cluster or episode schemas.
The application table count remains 31.

| Added field / constraint | Meaning |
|---|---|
| status TEXT NOT NULL, default published | Constrained to running/published/superseded/failed |
| started_at TIMESTAMPTZ NOT NULL | Wall-clock run start; legacy backfill uses calculated_at |
| completed_at TIMESTAMPTZ | Terminal wall-clock time; legacy backfill uses calculated_at |
| input_fingerprint TEXT nullable | 64-character captured logical assertion/source hash; legacy NULL |
| error_code TEXT nullable | shadow_failed/shadow_cancelled only; no exception diagnostics |
| ck_pattern_run_completion | running iff completed_at is NULL |
| ix_pattern_run_status(status,started_at) | Lifecycle inspection |

Existing policy/engine hashes, calculated_at, base assessment PK/FK, expected
counts and source references are preserved. Old artifacts receive published
lifecycle metadata without changing their calculations. New runs use explicit
running status; uncommitted or staged artifacts cannot be read as current.

Restore a verified pre-upgrade backup to a fresh DB for rollback. The migration
acceptance seeds a real 0003 run before upgrading to 0004, then checks its hashes,
timestamps and nullable new fields. The exact SQL is below.

```sql
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
```
