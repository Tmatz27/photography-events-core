"""Bounded business retention, separate from VACUUM; preserve decision provenance."""
from datetime import timedelta

from sqlalchemy import text


async def sweep(connection, now, batch_size=500):
    if not 1 <= batch_size <= 5000:
        raise ValueError("Retention batch must be between 1 and 5000")
    # Remove bulk blobs, but retain the adapter identity/enrichment contract for
    # explicit claims and aliased report IDs. Rejected claims must remain retryable
    # after a canonical correction, even after provider text is pruned.
    raw = await connection.execute(text("""UPDATE raw_observations r SET raw_payload=
        CASE WHEN raw_payload ? 'origin_namespace' OR raw_payload ? 'report_external_id'
        THEN (SELECT jsonb_object_agg(key,value) FROM jsonb_each(r.raw_payload)
            WHERE key IN ('external_id','origin_namespace','origin_external_id','report_external_id',
                'coordinate_uncertainty_meters','spatial_precision','credible','withdrawn','behavior','behaviors'))
            || '{"_m2_retained_metadata": true}'::jsonb
        ELSE NULL END
        WHERE id IN (SELECT id FROM raw_observations WHERE COALESCE(observed_at,fetched_at) < :cutoff AND raw_payload IS NOT NULL
        AND NOT raw_payload @> '{"_m2_retained_metadata": true}'::jsonb
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

