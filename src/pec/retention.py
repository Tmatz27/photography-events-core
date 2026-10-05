"""Bounded business retention, separate from VACUUM; preserve decision provenance."""
from datetime import timedelta

from sqlalchemy import text


async def sweep(connection, now, batch_size=500):
    if not 1 <= batch_size <= 5000:
        raise ValueError("Retention batch must be between 1 and 5000")
    # Retain relational evidence, but remove bulk provider blobs after 90 days.
    raw = await connection.execute(text("""UPDATE raw_observations SET raw_payload=NULL
        WHERE id IN (SELECT id FROM raw_observations WHERE COALESCE(observed_at,fetched_at) < :cutoff AND raw_payload IS NOT NULL
        ORDER BY fetched_at LIMIT :batch FOR UPDATE SKIP LOCKED)"""),
        {"cutoff": now - timedelta(days=90), "batch": batch_size})
    runs = await connection.execute(text("""DELETE FROM source_runs WHERE id IN (
        SELECT r.id FROM source_runs r WHERE completed_at < :cutoff
        AND NOT EXISTS(SELECT 1 FROM raw_observations o WHERE o.source_run_id=r.id)
        AND NOT EXISTS(SELECT 1 FROM opportunity_context_evidence e WHERE e.source_run_id=r.id)
        AND NOT EXISTS(SELECT 1 FROM legacy_context_evidence e WHERE e.source_run_id=r.id)
        AND NOT EXISTS(SELECT 1 FROM assessment_sources a WHERE a.source_run_id=r.id)
        AND NOT EXISTS(SELECT 1 FROM pattern_generation_sources p WHERE p.source_run_id=r.id)
        AND NOT EXISTS(SELECT 1 FROM normalized_observations n WHERE n.source_run_id=r.id)
        ORDER BY completed_at LIMIT :batch FOR UPDATE SKIP LOCKED)"""),
        {"cutoff": now - timedelta(days=90), "batch": batch_size})
    return {"payloads_redacted": raw.rowcount, "runs_deleted": runs.rowcount}

