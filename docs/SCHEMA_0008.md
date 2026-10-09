# Revision 0008: source fact lifecycle fences

Append-only successor of 0007. Migrations 0001–0007 are unchanged. No provider
table, performance index, partition, purge or M1/M2 analytical schema is added.

`source_poll_state.last_applied_poll_started_at` fences late poll completions.
`raw_observations.state_poll_started_at` is the accepted lifecycle watermark,
distinct from provider update, evidence time and successful retrieval time.
The source watermark is backfilled from its latest retained run start; each raw
watermark uses its retained run start, falling back to its fetched timestamp.

Raw `retired_at`, `retirement_reason`, `retirement_provider_updated_at` and
`retired_source_run_id` record absence, unavailability, inactivity or explicit
supersession. The provider-time fence applies to explicit CAP references, not
ordinary snapshot absence. Historical retired assertions are backfilled with
`legacy_retired`; the migration never fabricates a provider deletion reason.
Pre-0008 CAP references are also checked against retained provider payloads at
acceptance, so stale replay cannot erase a historical explicit cancellation.

`privacy_source_run_id` retains provenance for protection-only corrections whose
nonprivacy version was rejected. Run context records sanitized protection and
retirement events and invalid historical version metadata. These identifiers
remain internal; authenticated public diagnostics do not serialize them.
The retention sweep preserves referenced retirement/protection source runs.

`source_runs.reinstated` counts accepted active identities with no current
normalized assertion, separately from true duplicates, corrections and rejected
records. Reinstatement creates a new normalized assertion with original evidence
time and validity, preserves superseded history and cannot lower sensitivity.

Fresh, full-chain, repeat and backup/restore checks use head 0008. Chain acceptance
also seeds current/retired facts and invalid native clocks at 0007, then verifies
backfilled lifecycle fields and untouched evidence/native history at 0008.
Restore a verified pre-upgrade backup with its matching image to roll back;
downgrade is unsupported because it would discard lifecycle/provenance meaning.
