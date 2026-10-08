# Revision 0007: source-neutral public contract precision

Append-only successor of 0006; migrations 0001–0006 are unchanged. Existing
timestamp assertions keep their defaults and constraints. One new generic
`source_poll_state` table is added; no per-provider table or partition.

`normalized_observations` adds `observed_date`, `observed_time_zone` and
`time_precision`. An actual DATE requires observed_at NULL and date present;
timestamp/model precision requires observed_at present. No midnight/noon
observation instant is invented. Provider update is distinct from evidence
time; existing validity/supersession history remains. `source_metadata` is
fact/provenance JSONB, never executable analytical policy.

Spatial basis distinguishes unknown, open_point, obscured_cell,
private_unavailable and area_only. `analysis_area` accepts valid Polygon/
MultiPolygon in EPSG:4326; existing internal `analysis_geometry` stays Point.
Subject types also support safety and condition. Raw records gain
`provider_geometry`, spatial_basis and provider_updated_at; live provider
geometry is distinct from legacy exact_geometry and cannot become a public
destination. The adapter strips private fields and never obtains hidden points.

`source_runs` records contract/parser versions, request/byte counts, new identity/
correction/duplicate counts, privacy counts, 429 count, sanitized parser-code
counts and completeness. Existing received/accepted/rejected, native as-of,
latency/status fields remain authoritative. Generic polling state keeps the
incremental cursor, numeric refresh rotation, UTC daily request reservation
count and last reserved request slot. Its source FK cascades when a disposable
test deletes a source; production has no automatic source deletion policy.

The shadow generation ledger gains identity_rejected_count for L1. No M1
assessment or opportunity schema/production publication behavior is changed.
The migration adds no speculative performance index or destructive retention.

Upgrade uses the existing application role and transactional Alembic chain.
Downgrade is deliberately unsupported because earlier schemas cannot represent
the retained public-source precision/history. Restore a verified pre-upgrade
backup into a separate DB with its matching application image instead.
