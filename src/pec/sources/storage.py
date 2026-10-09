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

SOURCE_FINGERPRINT_SQL = """SELECT external_id,content_sha256,sensitive,
    retired_at IS NOT NULL AS retired,retirement_reason,retirement_provider_updated_at
    FROM raw_observations WHERE source_id=:sid ORDER BY external_id"""

# These are version-control decisions, never parser failures. Future clocks and
# malformed facts deliberately remain invalid and prevent certified completeness.
VERSION_SKIPS = frozenset({"stale_provider_update", "stale_reference_replay", "out_of_order_poll"})


async def source_fingerprint(c, sid):
    current = (await c.execute(text(SOURCE_FINGERPRINT_SQL), dict(sid=sid))).mappings()
    rows = [
        {key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items()}
        for row in current
    ]
    return fingerprint(rows)


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


async def elevate_privacy(c, sid, eid, now, rid):
    row = (
        (
            await c.execute(
                text(
                    "SELECT id,sensitive FROM raw_observations WHERE source_id=:sid AND external_id=:eid FOR UPDATE"
                ),
                dict(sid=sid, eid=eid),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return False
    precise = (
        await c.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM normalized_observations WHERE raw_observation_id=:raw AND superseded_at IS NULL AND analysis_geometry IS NOT NULL)"
            ),
            dict(raw=row["id"]),
        )
    ).scalar_one()
    await c.execute(
        text(
            "UPDATE raw_observations SET sensitive=TRUE,provider_geometry=NULL,exact_geometry=NULL WHERE id=:raw"
        ),
        dict(raw=row["id"]),
    )
    await c.execute(
        text(
            "UPDATE normalized_observations SET sensitive=TRUE,public_geometry=NULL,precision_class='withheld' WHERE raw_observation_id=:raw"
        ),
        dict(raw=row["id"]),
    )
    # Preserve historical source assertion geometry/meaning internally; remove
    # the CURRENT native analysis point so privacy-only updates cannot cluster.
    await c.execute(
        text(
            "UPDATE normalized_observations SET analysis_geometry=NULL,spatial_precision='unknown' WHERE raw_observation_id=:raw AND superseded_at IS NULL"
        ),
        dict(raw=row["id"]),
    )
    changed = not row["sensitive"] or precise
    if changed:
        await c.execute(
            text(
                "UPDATE raw_observations SET privacy_source_run_id=COALESCE(:rid,privacy_source_run_id) WHERE id=:raw"
            ),
            dict(raw=row["id"], rid=rid),
        )
    return changed


def future_update(contract, stamp, reference):
    return stamp is not None and stamp > reference + timedelta(seconds=contract.provider_clock_skew_seconds)


async def withdraw(
    c, sid, eid, now, *, protect=False, started=None, rid=None, reason="corrected", provider_time=None
):
    raw = (
        await c.execute(
            text("SELECT id FROM raw_observations WHERE source_id=:sid AND external_id=:eid"),
            dict(sid=sid, eid=eid),
        )
    ).scalar_one_or_none()
    if raw is None:
        return
    if protect:
        await elevate_privacy(c, sid, eid, now, rid)
    await c.execute(
        text(
            "UPDATE normalized_observations SET superseded_at=:now WHERE raw_observation_id=:raw AND superseded_at IS NULL"
        ),
        dict(raw=raw, now=now),
    )
    if reason != "corrected":
        await c.execute(
            text("""UPDATE raw_observations SET retired_at=:now,retirement_reason=:reason,
            state_poll_started_at=GREATEST(state_poll_started_at,:started),retired_source_run_id=:rid,
            retirement_provider_updated_at=GREATEST(retirement_provider_updated_at,:provider)
            WHERE id=:raw"""),
            dict(raw=raw, now=now, reason=reason, started=started or now, rid=rid, provider=provider_time),
        )
    await c.execute(
        text("""UPDATE observation_report_group_members m SET superseded_at=GREATEST(:now,m.created_at)
        FROM normalized_observations n WHERE n.id=m.normalized_observation_id
        AND n.raw_observation_id=:raw AND n.superseded_at IS NOT NULL AND m.superseded_at IS NULL"""),
        dict(raw=raw, now=now),
    )


async def store_fact(c, contract, sid, rid, fact, now, *, started=None, ordered=True):
    started = started or now
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
    if future_update(contract, fact.provider_updated_at, started):
        raise RecordError("future_provider_update")
    if not ordered or (
        previous and previous["state_poll_started_at"] and previous["state_poll_started_at"] > started
    ):
        raise RecordError("out_of_order_poll")
    old_update = previous["provider_updated_at"] if previous else None
    invalid_previous = bool(previous and future_update(contract, old_update, previous["fetched_at"]))
    if invalid_previous:
        old_update = None  # Invalid historical metadata cannot be a version fence.
    if old_update and old_update > fact.provider_updated_at:
        raise RecordError("stale_provider_update")
    if (
        previous
        and previous["retirement_provider_updated_at"]
        and fact.provider_updated_at <= previous["retirement_provider_updated_at"]
    ):
        raise RecordError("stale_reference_replay")
    if contract.source_key == "nws_live_context" and fact.subject_key == "nws_alert":
        # Recover barriers from retained pre-0008 CAP bodies too. These are
        # explicit provider references, never fuzzy time/species relationships.
        barrier = (
            await c.execute(
                text("""SELECT max(r.provider_updated_at) FROM raw_observations r
            WHERE source_id=:sid AND r.raw_payload->'properties'->>'messageType' IN ('Cancel','Update')
            AND r.provider_updated_at<=r.fetched_at+make_interval(secs=>:skew)
            AND EXISTS(SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(r.raw_payload->'properties'->'references')='array'
            THEN r.raw_payload->'properties'->'references' ELSE '[]'::jsonb END) p
            WHERE p->>'identifier'=:eid)"""),
                dict(sid=sid, eid=fact.external_id, skew=contract.provider_clock_skew_seconds),
            )
        ).scalar_one()
        if barrier and fact.provider_updated_at <= barrier:
            raise RecordError("stale_reference_replay")
    current = (
        await c.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM normalized_observations WHERE raw_observation_id=:raw AND superseded_at IS NULL)"
            ),
            dict(raw=previous["id"] if previous else None),
        )
    ).scalar_one()
    active = fact.in_scope and fact.metadata.get("active", True)
    reinstated = bool(previous and not current and active)
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
    changed = (
        not previous
        or previous["content_sha256"] != digest
        or previous["raw_payload"] is None
        or reinstated
        or invalid_previous
    )
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
        started=started,
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
    await c.execute(
        text("UPDATE raw_observations SET state_poll_started_at=:started WHERE id=:raw"),
        dict(raw=raw, started=started),
    )
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
        await c.execute(
            text(
                "UPDATE raw_observations SET retired_at=NULL,retirement_reason=NULL,retirement_provider_updated_at=NULL,retired_source_run_id=NULL WHERE id=:raw"
            ),
            dict(raw=raw),
        )
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
    else:
        await withdraw(c, sid, fact.external_id, now, started=started, rid=rid, reason="provider_inactive")
    for eid in fact.metadata.get("supersedes", []):
        await withdraw(
            c,
            sid,
            eid,
            now,
            started=started,
            rid=rid,
            reason="explicit_reference",
            provider_time=fact.provider_updated_at,
        )
    return "reinstated" if reinstated else "corrections" if previous else "unique_records"


async def persist(db, contract, batch, started, completed):
    async def operation(c):
        await db._check(c)
        sid = await register(c, contract)
        # Serializes only this live source's short DB mutation, without M1's lock.
        state = (
            (
                await c.execute(
                    text("SELECT * FROM source_poll_state WHERE source_id=:sid FOR UPDATE"), dict(sid=sid)
                )
            )
            .mappings()
            .one()
        )
        ordered = (
            state["last_applied_poll_started_at"] is None or started > state["last_applied_poll_started_at"]
        )
        if not ordered:
            batch.complete = False
            batch.failure_code = "out_of_order_poll"
        if future_update(contract, batch.provider_updated_at, started):
            batch.complete = False
            batch.failure_code = "future_provider_update"
            batch.provider_updated_at = max(
                (
                    f.provider_updated_at
                    for f in batch.records
                    if not future_update(contract, f.provider_updated_at, started)
                ),
                default=None,
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
        skips = Counter()
        protection_events = []
        invalid_historical_versions = []
        seen = []
        snapshot_seen = []
        for fact in batch.records:
            # Transport records are features; incident identity is the union.
            weight = (
                len(fact.payload.get("pieces", [fact.payload]))
                if contract.source_key == "wfigs_current"
                else 1
            )
            old = (
                (
                    await c.execute(
                        text(
                            "SELECT provider_updated_at,fetched_at FROM raw_observations WHERE source_id=:sid AND external_id=:eid"
                        ),
                        dict(sid=sid, eid=fact.external_id),
                    )
                )
                .mappings()
                .first()
            )
            if old and future_update(contract, old["provider_updated_at"], old["fetched_at"]):
                invalid_historical_versions.append(fact.external_id)
            # Protection is independent of acceptance order and outside the
            # savepoint: a rejected older/future version may only raise privacy.
            if fact.sensitive and await elevate_privacy(c, sid, fact.external_id, completed, rid):
                protection_events.append(
                    dict(
                        external_id=fact.external_id,
                        provider_updated_at=fact.provider_updated_at.isoformat(),
                        spatial_basis=fact.spatial_basis,
                    )
                )
            try:
                async with c.begin_nested():
                    disposition = await store_fact(
                        c, contract, sid, rid, fact, completed, started=started, ordered=ordered
                    )
            except (RecordError, IntegrityError, DataError) as exc:
                code = exc.code if isinstance(exc, RecordError) else "invalid_database_fact"
                if code in VERSION_SKIPS:
                    batch.skipped.extend((fact.external_id, code) for _ in range(weight))
                    skips[code] += weight
                    # Presence is independent of whether an older version can
                    # replace the accepted assertion. This never reactivates it;
                    # explicit CAP references still retire it in either order.
                    snapshot_seen.append(fact.external_id)
                else:
                    batch.rejected.extend((fact.external_id, code) for _ in range(weight))
                    errors[code] += weight
            else:
                counts["accepted"] += weight
                counts[disposition] += 1
                counts["obscured_records"] += fact.spatial_basis == "obscured_cell"
                counts["private_records"] += fact.spatial_basis == "private_unavailable"
                seen.append(fact.external_id)
                snapshot_seen.append(fact.external_id)
        for eid, code in batch.rejected:
            event("parser_failure", source=contract.source_key, code=code)
            if eid and code not in (
                "future_provider_update",
                "stale_provider_update",
                "stale_reference_replay",
                "out_of_order_poll",
            ):
                # Unreadable corrected state must not preserve an old precise fact.
                if ordered:
                    await withdraw(
                        c,
                        sid,
                        eid,
                        completed,
                        protect=True,
                        started=started,
                        rid=rid,
                        reason="invalid_record",
                    )
                else:
                    await elevate_privacy(c, sid, eid, completed, rid)
        for eid in batch.unavailable_ids:
            if ordered:
                await withdraw(
                    c,
                    sid,
                    eid,
                    completed,
                    protect=True,
                    started=started,
                    rid=rid,
                    reason="public_unavailable",
                )
            elif await elevate_privacy(c, sid, eid, completed, rid):
                protection_events.append(dict(external_id=eid, basis="public_unavailable"))
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
                if ordered:
                    await withdraw(
                        c,
                        sid,
                        eid,
                        completed,
                        protect=True,
                        started=started,
                        rid=rid,
                        reason="invalid_record",
                    )
                else:
                    await elevate_privacy(c, sid, eid, completed, rid)
        complete = bool(ordered and batch.complete and not errors and not batch.failure_code)
        # Collection HTTP/backoff and refresh rotation must use the effective
        # outcome, not the transport's pre-persistence completeness flag.
        batch.complete = complete
        if complete and batch.snapshot:
            missing = (
                (
                    await c.execute(
                        text("""SELECT DISTINCT r.external_id FROM raw_observations r
                JOIN normalized_observations n ON n.raw_observation_id=r.id
                WHERE r.source_id=:sid AND n.superseded_at IS NULL AND r.fetched_at<=:started
                AND NOT r.external_id=ANY(CAST(:seen AS text[]))"""),
                        dict(sid=sid, started=started, seen=snapshot_seen),
                    )
                )
                .scalars()
                .all()
            )
            for eid in missing:
                await withdraw(c, sid, eid, completed, started=started, rid=rid, reason="snapshot_absent")
        # Cursor advances only a fully traversed, fully readable observation poll.
        if complete:
            await c.execute(
                text("""UPDATE source_poll_state SET cursor_updated_at=GREATEST(cursor_updated_at,:started)
                WHERE source_id=:sid"""),
                dict(sid=sid, started=started),
            )
        if ordered:
            await c.execute(
                text(
                    "UPDATE source_poll_state SET last_applied_poll_started_at=:started WHERE source_id=:sid"
                ),
                dict(sid=sid, started=started),
            )
        digest = await source_fingerprint(c, sid)
        retirement_events = (
            await c.execute(
                text(
                    "SELECT external_id,retirement_reason,retirement_provider_updated_at FROM raw_observations WHERE retired_source_run_id=:rid"
                ),
                dict(rid=rid),
            )
        ).mappings()
        retirement_events = [
            {key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items()}
            for row in retirement_events
        ]
        status = (
            "failure" if not ordered else "success" if complete else "parser_failure" if errors else "failure"
        )
        context = canonical(
            dict(
                seen_ids=sorted(set(seen)),
                snapshot_seen_ids=sorted(set(snapshot_seen)) if ordered else [],
                skip_reason_counts=dict(skips),
                poll_outcome="ignored_out_of_order_poll"
                if not ordered
                else "complete"
                if complete
                else "incomplete",
                outcome_counts=dict(
                    accepted=counts["accepted"],
                    duplicate=counts["duplicates"],
                    reinstated=counts["reinstated"],
                    rejected_invalid=len(batch.rejected),
                    skipped_stale_version=skips["stale_provider_update"]
                    + (skips["out_of_order_poll"] if ordered else 0),
                    skipped_replay=skips["stale_reference_replay"],
                    ignored_out_of_order_poll=int(not ordered),
                    incomplete_snapshot=int(batch.snapshot and not complete),
                ),
                alert_asof=batch.alert_asof.isoformat() if batch.alert_asof else None,
                complete_snapshot=bool(complete and batch.snapshot),
                protection_events=protection_events,
                invalid_historical_versions=invalid_historical_versions,
                retirement_events=retirement_events,
                public_unavailable_ids=sorted(batch.unavailable_ids),
            )
        )
        await c.execute(
            text("""UPDATE source_runs SET records_accepted=:accepted,records_rejected=:rejected,
            unique_records=:unique,corrections=:corrections,duplicates=:duplicates,reinstated=:reinstated,obscured_records=:obscured,
            private_records=:private,parser_error_counts=CAST(:errors AS jsonb),status=:status,error_code=:error,
            incomplete=:incomplete,content_sha256=:digest,context_payload=CAST(:context AS jsonb) WHERE id=:rid"""),
            dict(
                accepted=counts["accepted"],
                rejected=len(batch.rejected),
                unique=counts["unique_records"],
                corrections=counts["corrections"],
                duplicates=counts["duplicates"],
                reinstated=counts["reinstated"],
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
