"""Live facts commit only through the isolated shadow pool, never the M1 lock."""

import asyncio
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DataError

from ..ingestion import canonical, fingerprint
from ..logging import event
from .http import Client, FetchError
from .fetch import fetch
from .models import RecordError, Batch


async def register(c, contract):
    sid = (
        await c.execute(
            text("""INSERT INTO sources(key,name,source_type,requires_stable_ids)
        VALUES(:key,:name,'public_api_shadow',TRUE) ON CONFLICT(key) DO UPDATE SET name=EXCLUDED.name RETURNING id"""),
            {"key": contract.source_key, "name": contract.provider_name},
        )
    ).scalar_one()
    for role in contract.roles:
        await c.execute(
            text("INSERT INTO source_roles VALUES(:sid,:role) ON CONFLICT DO NOTHING"),
            {"sid": sid, "role": role},
        )
    await c.execute(
        text("INSERT INTO source_poll_state(source_id) VALUES(:sid) ON CONFLICT DO NOTHING"), {"sid": sid}
    )
    return sid


async def reserve(db, contract):
    """Durable daily quota and spaced reservations survive process restarts."""
    now = datetime.now(UTC)

    async def operation(c):
        sid = await register(c, contract)
        row = (
            (
                await c.execute(
                    text("SELECT * FROM source_poll_state WHERE source_id=:sid FOR UPDATE"), {"sid": sid}
                )
            )
            .mappings()
            .one()
        )
        used = row["requests_today"] if row["quota_day"] == now.date() else 0
        slot = max(
            now,
            (row["last_request_at"] or now - timedelta(days=1))
            + timedelta(seconds=contract.request_spacing_seconds),
        )
        # Do not reserve future-day requests under today's budget.
        if used >= contract.requests_per_day or slot.date() != now.date():
            delay = (
                (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) - now
            ).total_seconds()
            raise FetchError("daily_request_budget", 429, str(int(delay) + 1))
        await c.execute(
            text("""UPDATE source_poll_state SET quota_day=:day,requests_today=:used,
            last_request_at=:slot WHERE source_id=:sid"""),
            dict(day=now.date(), used=used + 1, slot=slot, sid=sid),
        )
        return slot

    slot = await db.pattern_transaction(operation, write=True)
    await asyncio.sleep(max(0, (slot - datetime.now(UTC)).total_seconds()))


async def withdraw(c, sid, eid, now, *, protect=False):
    raw = (
        await c.execute(
            text("SELECT id FROM raw_observations WHERE source_id=:sid AND external_id=:eid"),
            dict(sid=sid, eid=eid),
        )
    ).scalar_one_or_none()
    if raw is None:
        return
    await c.execute(
        text(
            "UPDATE normalized_observations SET superseded_at=:now WHERE raw_observation_id=:raw AND superseded_at IS NULL"
        ),
        dict(raw=raw, now=now),
    )
    if protect:
        await c.execute(
            text(
                "UPDATE raw_observations SET sensitive=TRUE,provider_geometry=NULL,exact_geometry=NULL WHERE id=:raw"
            ),
            dict(raw=raw),
        )
        await c.execute(
            text(
                "UPDATE normalized_observations SET sensitive=TRUE,public_geometry=NULL,precision_class='withheld' WHERE raw_observation_id=:raw"
            ),
            dict(raw=raw),
        )
    await c.execute(
        text("""UPDATE observation_report_group_members m SET superseded_at=GREATEST(:now,m.created_at)
        FROM normalized_observations n WHERE n.id=m.normalized_observation_id
        AND n.raw_observation_id=:raw AND n.superseded_at IS NOT NULL AND m.superseded_at IS NULL"""),
        dict(raw=raw, now=now),
    )


async def store_fact(c, contract, sid, rid, fact, now):
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
    if previous and (
        previous["fetched_at"] > now
        or (previous["provider_updated_at"] and previous["provider_updated_at"] > fact.provider_updated_at)
    ):
        return "duplicates"
    digest = fingerprint(
        dict(
            payload=fact.payload,
            metadata=fact.metadata,
            in_scope=fact.in_scope,
            observed_at=fact.observed_at.isoformat() if fact.observed_at else None,
            observed_date=fact.observed_date.isoformat() if fact.observed_date else None,
            provider_updated_at=fact.provider_updated_at.isoformat(),
            time_precision=fact.time_precision,
            spatial_basis=fact.spatial_basis,
            parser_version=contract.parser_version,
        )
    )
    sensitive = fact.sensitive or bool(previous and previous["sensitive"])
    changed = not previous or previous["content_sha256"] != digest or previous["raw_payload"] is None
    if fact.analysis_area:
        valid = (
            await c.execute(
                text("SELECT ST_IsValid(ST_GeomFromGeoJSON(:geometry))"),
                {"geometry": canonical(fact.analysis_area)},
            )
        ).scalar_one()
        # Incident pieces may overlap; validate each ring-bearing piece first,
        # then union legitimate overlapping pieces. Never repair invalid rings.
        if not valid and fact.analysis_area["type"] == "MultiPolygon":
            for coordinates in fact.analysis_area["coordinates"]:
                good = (
                    await c.execute(
                        text("SELECT ST_IsValid(ST_GeomFromGeoJSON(:geometry))"),
                        {"geometry": canonical(dict(type="Polygon", coordinates=coordinates))},
                    )
                ).scalar_one()
                if not good:
                    raise RecordError("invalid_polygon_topology")
        elif not valid:
            raise RecordError("invalid_polygon_topology")
    params = dict(
        sid=sid,
        rid=rid,
        eid=fact.external_id,
        observed=fact.observed_at,
        now=now,
        payload=canonical(fact.payload),
        digest=digest,
        sensitive=sensitive,
        version=contract.parser_version,
        geometry=canonical(fact.provider_geometry) if fact.provider_geometry else None,
        basis=fact.spatial_basis,
        updated=fact.provider_updated_at,
    )
    raw = (
        await c.execute(
            text("""INSERT INTO raw_observations(source_id,source_run_id,external_id,observed_at,fetched_at,
        raw_payload,parser_version,content_sha256,sensitive,provider_geometry,spatial_basis,provider_updated_at)
        VALUES(:sid,:rid,:eid,:observed,:now,CAST(:payload AS jsonb),:version,:digest,:sensitive,
        ST_GeomFromGeoJSON(:geometry),:basis,:updated) ON CONFLICT(source_id,external_id) DO UPDATE SET
        source_run_id=EXCLUDED.source_run_id,observed_at=EXCLUDED.observed_at,fetched_at=EXCLUDED.fetched_at,
        raw_payload=EXCLUDED.raw_payload,parser_version=EXCLUDED.parser_version,content_sha256=EXCLUDED.content_sha256,
        sensitive=EXCLUDED.sensitive,provider_geometry=EXCLUDED.provider_geometry,spatial_basis=EXCLUDED.spatial_basis,
        provider_updated_at=EXCLUDED.provider_updated_at RETURNING id"""),
            params,
        )
    ).scalar_one()
    if not changed:
        return "duplicates"
    await withdraw(c, sid, fact.external_id, now, protect=sensitive)
    # Protected provider public geometry may be retained with its honest basis;
    # raw exact_geometry remains NULL. Historical product protection only rises.
    await c.execute(
        text("UPDATE raw_observations SET provider_geometry=ST_GeomFromGeoJSON(:geometry) WHERE id=:raw"),
        dict(raw=raw, geometry=params["geometry"]),
    )
    if fact.in_scope and fact.metadata.get("active", True):
        point = fact.analysis_point if not sensitive else None
        p = {
            **params,
            "raw": raw,
            "subject": fact.subject_key,
            "kind": fact.subject_type,
            "date": fact.observed_date,
            "zone": fact.observed_time_zone,
            "precision": fact.time_precision,
            "valid": fact.valid_until,
            "lon": point[0] if point else None,
            "lat": point[1] if point else None,
            "accuracy": fact.uncertainty,
            "credible": fact.credible,
            "metadata": canonical(fact.metadata),
            "area": canonical(fact.analysis_area) if fact.analysis_area else None,
        }
        await c.execute(
            text("""INSERT INTO normalized_observations(raw_observation_id,subject_type,subject_key,
            observed_at,observed_date,observed_time_zone,time_precision,valid_until,analysis_geometry,analysis_area,
            sensitive,precision_class,reported_count,source_run_id,content_sha256,provider_updated_at,source_metadata,
            spatial_basis,spatial_precision,coordinate_uncertainty_meters,credible)
            VALUES(:raw,:kind,:subject,:observed,:date,:zone,:precision,:valid,
            ST_SetSRID(ST_MakePoint(:lon,:lat),4326),ST_UnaryUnion(ST_GeomFromGeoJSON(:area)),
            :sensitive,'withheld',NULL,:rid,:digest,:updated,CAST(:metadata AS jsonb),:basis,
            CASE WHEN :lon IS NOT NULL THEN 'point' ELSE 'unknown' END,:accuracy,:credible)"""),
            p,
        )
    for eid in fact.metadata.get("supersedes", []):
        await withdraw(c, sid, eid, now)
    return "corrections" if previous else "unique_records"


async def persist(db, contract, batch, started, completed):
    async def operation(c):
        await db._check(c)
        sid = await register(c, contract)
        # Serializes only this live source's short DB mutation, without M1's lock.
        await c.execute(
            text("SELECT source_id FROM source_poll_state WHERE source_id=:sid FOR UPDATE"), dict(sid=sid)
        )
        rid = (
            await c.execute(
                text("""INSERT INTO source_runs(source_id,cycle_key,attempt_number,started_at,completed_at,
            status,records_received,provider_updated_at,http_status,contract_version,parser_version,requests,bytes_received,
            rate_limit_count,latency_ms) VALUES(:sid,:cycle,1,:started,:completed,'failure',:received,:updated,:http,
            :version,:parser,:requests,:bytes,:rates,:latency) RETURNING id"""),
                dict(
                    sid=sid,
                    cycle=str(uuid.uuid4()),
                    started=started,
                    completed=completed,
                    received=batch.received,
                    updated=batch.provider_updated_at,
                    http=batch.http_status,
                    version=contract.version,
                    parser=contract.parser_version,
                    requests=batch.requests,
                    bytes=batch.bytes_received,
                    rates=batch.rate_limited,
                    latency=max(0, int((completed - started).total_seconds() * 1000)),
                ),
            )
        ).scalar_one()
        counts = Counter()
        errors = Counter(code for _, code in batch.rejected)
        seen = []
        for fact in batch.records:
            # Transport records are features; incident identity is the union.
            weight = (
                len(fact.payload.get("pieces", [fact.payload]))
                if contract.source_key == "wfigs_current"
                else 1
            )
            try:
                async with c.begin_nested():
                    disposition = await store_fact(c, contract, sid, rid, fact, completed)
            except (RecordError, IntegrityError, DataError) as exc:
                code = exc.code if isinstance(exc, RecordError) else "invalid_database_fact"
                batch.rejected.extend((fact.external_id, code) for _ in range(weight))
                errors[code] += weight
            else:
                counts["accepted"] += weight
                counts[disposition] += 1
                counts["obscured_records"] += fact.spatial_basis == "obscured_cell"
                counts["private_records"] += fact.spatial_basis == "private_unavailable"
                seen.append(fact.external_id)
        for eid, code in batch.rejected:
            event("parser_failure", source=contract.source_key, code=code)
            if eid:
                # Unreadable corrected state must not preserve an old precise fact.
                await withdraw(c, sid, eid, completed, protect=True)
        for eid in batch.unavailable_ids:
            await withdraw(c, sid, eid, completed, protect=True)
        if contract.source_key == "inaturalist" and batch.invalid_numeric_ids:
            # The documented numeric ID can identify a previously known record
            # even when this unreadable correction lost its UUID. It is only
            # a withdrawal/protection lookup, never a synthetic new identity.
            unreadable = (
                (
                    await c.execute(
                        text("""SELECT DISTINCT r.external_id FROM raw_observations r
                JOIN normalized_observations n ON n.raw_observation_id=r.id WHERE r.source_id=:sid
                AND (n.source_metadata->>'provider_numeric_id')::bigint=ANY(CAST(:ids AS bigint[]))"""),
                        dict(sid=sid, ids=sorted(batch.invalid_numeric_ids)),
                    )
                )
                .scalars()
                .all()
            )
            for eid in unreadable:
                await withdraw(c, sid, eid, completed, protect=True)
        complete = batch.complete and not errors
        if complete and batch.snapshot:
            missing = (
                (
                    await c.execute(
                        text("""SELECT DISTINCT r.external_id FROM raw_observations r
                JOIN normalized_observations n ON n.raw_observation_id=r.id
                WHERE r.source_id=:sid AND n.superseded_at IS NULL AND r.fetched_at<=:started
                AND NOT r.external_id=ANY(CAST(:seen AS text[]))"""),
                        dict(sid=sid, started=started, seen=seen),
                    )
                )
                .scalars()
                .all()
            )
            for eid in missing:
                await withdraw(c, sid, eid, completed)
        # Cursor advances only a fully traversed, fully readable observation poll.
        if complete:
            await c.execute(
                text("""UPDATE source_poll_state SET cursor_updated_at=GREATEST(cursor_updated_at,:started)
                WHERE source_id=:sid"""),
                dict(sid=sid, started=started),
            )
        current = (
            await c.execute(
                text(
                    "SELECT external_id,content_sha256,sensitive FROM raw_observations WHERE source_id=:sid ORDER BY external_id"
                ),
                dict(sid=sid),
            )
        ).mappings()
        digest = fingerprint([dict(r) for r in current])
        status = "success" if complete else "parser_failure" if errors else "failure"
        context = canonical(
            dict(
                seen_ids=sorted(set(seen)),
                alert_asof=batch.alert_asof.isoformat() if batch.alert_asof else None,
            )
        )
        await c.execute(
            text("""UPDATE source_runs SET records_accepted=:accepted,records_rejected=:rejected,
            unique_records=:unique,corrections=:corrections,duplicates=:duplicates,obscured_records=:obscured,
            private_records=:private,parser_error_counts=CAST(:errors AS jsonb),status=:status,error_code=:error,
            incomplete=:incomplete,content_sha256=:digest,context_payload=CAST(:context AS jsonb) WHERE id=:rid"""),
            dict(
                accepted=counts["accepted"],
                rejected=len(batch.rejected),
                unique=counts["unique_records"],
                corrections=counts["corrections"],
                duplicates=counts["duplicates"],
                obscured=counts["obscured_records"],
                private=counts["private_records"],
                errors=canonical(errors),
                status=status,
                error=batch.failure_code or ("record_rejected" if errors else None),
                incomplete=not complete,
                digest=digest,
                context=context,
                rid=rid,
            ),
        )
        return rid

    return await db.pattern_transaction(operation, write=True)


async def collect(db, contract, user_agent, *, client=None, clock=lambda: datetime.now(UTC)):
    started = clock()

    async def state(c):
        sid = await register(c, contract)
        enabled = (
            await c.execute(text("SELECT enabled FROM sources WHERE id=:sid"), dict(sid=sid))
        ).scalar_one()
        row = (
            (await c.execute(text("SELECT * FROM source_poll_state WHERE source_id=:sid"), dict(sid=sid)))
            .mappings()
            .one()
        )
        known = {}
        if contract.source_key == "inaturalist":
            values = (
                (
                    await c.execute(
                        text("""SELECT r.external_id,(n.source_metadata->>'provider_numeric_id')::bigint AS pid
                FROM raw_observations r JOIN normalized_observations n ON n.raw_observation_id=r.id
                WHERE r.source_id=:sid AND n.superseded_at IS NULL AND n.valid_until>=:now
                AND (n.source_metadata->>'provider_numeric_id')::bigint>:after ORDER BY pid LIMIT 200"""),
                        dict(sid=sid, now=started, after=row["refresh_after_id"]),
                    )
                )
                .mappings()
                .all()
            )
            known = {v["pid"]: v["external_id"] for v in values}
        return enabled, row["cursor_updated_at"], known

    enabled, cursor, known = await db.pattern_transaction(state, write=True)
    if not enabled:
        return 503, None
    client = client or Client(contract, user_agent, reserve=lambda: reserve(db, contract))
    try:
        batch = await fetch(contract, client, started, cursor=cursor, known=known)
    except asyncio.CancelledError:
        # Scheduler deadline/shutdown remains cancellation, with a truthful
        # failed attempt rather than a success/empty snapshot. No M1 resources.
        failed = Batch(
            complete=False,
            http_status=503,
            failure_code="collection_cancelled",
            requests=client.requests,
            bytes_received=client.bytes_received,
            rate_limited=client.rate_limited,
        )
        await asyncio.shield(persist(db, contract, failed, started, clock()))
        raise
    await persist(db, contract, batch, started, clock())
    if batch.complete and not batch.rejected and contract.source_key == "inaturalist":

        async def rotate(c):
            await c.execute(
                text(
                    "UPDATE source_poll_state SET refresh_after_id=:after WHERE source_id=(SELECT id FROM sources WHERE key=:key)"
                ),
                dict(after=max(known) if len(known) == 200 else 0, key=contract.source_key),
            )

        await db.pattern_transaction(rotate, write=True)
    return (
        batch.http_status
        if batch.http_status != 200
        else 200
        if batch.complete and not batch.rejected
        else 502
    ), batch.retry_after
