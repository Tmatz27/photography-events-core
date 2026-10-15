"""Environmental revisions share raw identity across live and history workers."""

from sqlalchemy import text

from ..ingestion import canonical, fingerprint
from .environment_contracts import ENVIRONMENT_CONTRACTS, base_key
from .models import RecordError


async def store(c, contract, sid, rid, fact, now, started, ordered):
    from .storage import register, future_update

    if base_key(contract.source_key) != fact.dataset_key:
        raise RecordError("environment_dataset_mismatch")
    if contract.source_key.endswith("_history"):
        sid = await register(c, ENVIRONMENT_CONTRACTS[fact.dataset_key])
        # History and incremental workers share the SAME native identity rows.
        await c.execute(
            text("SELECT source_id FROM source_poll_state WHERE source_id=:sid FOR UPDATE"), dict(sid=sid)
        )
    previous = (
        (
            await c.execute(
                text("SELECT * FROM raw_observations WHERE source_id=:sid AND external_id=:eid FOR UPDATE"),
                dict(sid=sid, eid=fact.external_id),
            )
        )
        .mappings()
        .first()
    )
    if not ordered or (
        previous and previous["state_poll_started_at"] and previous["state_poll_started_at"] > started
    ):
        raise RecordError("out_of_order_poll")
    if future_update(contract, fact.provider_updated_at, started):
        raise RecordError("future_provider_update")
    if (
        previous
        and previous["provider_updated_at"]
        and fact.provider_updated_at
        and previous["provider_updated_at"] > fact.provider_updated_at
    ):
        raise RecordError("stale_provider_update")
    if fact.evidence_kind == "measurement" and fact.valid_at > started:
        raise RecordError("future_measurement_time")
    if fact.issued_at and future_update(contract, fact.issued_at, started):
        raise RecordError("future_forecast_issue_time")
    metadata = {
        **fact.metadata,
        "station_id": fact.station_id,
        "quantity": fact.quantity,
        "evidence_kind": fact.evidence_kind,
        "native_value": fact.native_value,
        "unit": fact.unit,
        "valid_at": fact.valid_at.isoformat() if fact.valid_at else None,
        "issued_at": fact.issued_at.isoformat() if fact.issued_at else None,
        "upstream_lineage": fact.dataset_key,
        "withdrawn": fact.withdrawn,
    }
    digest = fingerprint(
        dict(
            payload=fact.payload,
            metadata=metadata,
            parser=contract.parser_version,
            provider_updated_at=fact.provider_updated_at.isoformat() if fact.provider_updated_at else None,
        )
    )
    changed = not previous or previous["content_sha256"] != digest
    params = dict(
        sid=sid,
        rid=rid,
        eid=fact.external_id,
        observed=fact.observed_at,
        now=now,
        payload=canonical(fact.payload),
        parser=contract.parser_version,
        digest=digest,
        geometry=canonical(fact.provider_geometry) if fact.provider_geometry else None,
        updated=fact.provider_updated_at,
        started=started,
    )
    raw = (
        await c.execute(
            text("""INSERT INTO raw_observations(source_id,source_run_id,external_id,
        observed_at,fetched_at,raw_payload,parser_version,content_sha256,sensitive,provider_geometry,
        provider_updated_at,state_poll_started_at) VALUES(:sid,:rid,:eid,:observed,:now,
        CAST(:payload AS jsonb),:parser,:digest,FALSE,ST_GeomFromGeoJSON(:geometry),:updated,:started)
        ON CONFLICT(source_id,external_id) DO UPDATE SET source_run_id=EXCLUDED.source_run_id,
        fetched_at=EXCLUDED.fetched_at,raw_payload=EXCLUDED.raw_payload,content_sha256=EXCLUDED.content_sha256,
        parser_version=EXCLUDED.parser_version,observed_at=EXCLUDED.observed_at,
        provider_geometry=EXCLUDED.provider_geometry,provider_updated_at=EXCLUDED.provider_updated_at,
        state_poll_started_at=EXCLUDED.state_poll_started_at RETURNING id"""),
            params,
        )
    ).scalar_one()
    if not changed:
        await c.execute(
            text(
                "UPDATE environmental_assertions SET last_received_at=:now WHERE raw_observation_id=:raw AND superseded_at IS NULL"
            ),
            dict(now=now, raw=raw),
        )
        return "duplicates"
    await c.execute(
        text(
            "UPDATE environmental_assertions SET superseded_at=:now WHERE raw_observation_id=:raw AND superseded_at IS NULL"
        ),
        dict(now=now, raw=raw),
    )
    await c.execute(
        text("""INSERT INTO environmental_assertions(raw_observation_id,source_run_id,dataset_key,
        station_id,quantity,evidence_kind,observed_at,valid_at,issued_at,provider_updated_at,
        native_value,numeric_value,unit,quality,provider_geometry,metadata,raw_payload,
        content_sha256,recorded_at,last_received_at,withdrawn)
        VALUES(:raw,:rid,:dataset,:station,:quantity,:kind,:observed,:valid,:issued,:updated,
        :native,:value,:unit,CAST(:quality AS jsonb),ST_GeomFromGeoJSON(:geometry),CAST(:metadata AS jsonb),
        CAST(:payload AS jsonb),:digest,:now,:now,:withdrawn)"""),
        {
            **params,
            "raw": raw,
            "dataset": fact.dataset_key,
            "station": fact.station_id,
            "quantity": fact.quantity,
            "kind": fact.evidence_kind,
            "valid": fact.valid_at,
            "issued": fact.issued_at,
            "native": fact.native_value,
            "value": fact.numeric_value,
            "unit": fact.unit,
            "quality": canonical(fact.metadata["quality"]),
            "metadata": canonical(metadata),
            "withdrawn": fact.withdrawn,
        },
    )
    return "corrections" if previous else "unique_records"
