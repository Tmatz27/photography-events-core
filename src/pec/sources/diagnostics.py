"""Ingestion inventory diagnostics: counts/status only, no provider secrets or coordinates."""
from datetime import datetime
from typing import Literal

from sqlalchemy import text

from ..schemas import Contract

from .contracts import CONTRACTS
from .inventory import PROVIDERS, configured


class Operational(Contract):
    key: str
    enabled: bool
    lease_until: datetime | None
    cursor_updated_at: datetime | None
    next_allowed_at: datetime | None
    consecutive_failures: int | None
    status: str | None
    incomplete: bool | None
    records_accepted: int | None
    error_code: str | None
    completed_at: datetime | None
    provider_updated_at: datetime | None
    raw_identities: int
    historical_assertions: int


class ProviderView(Contract):
    key: str
    provider: str
    batch: int
    kind: Literal['live','event','reference','group']
    measurements: tuple[str, ...]
    evidence_kind: str
    ranked_priority: int | None
    retention_policy: str
    historical_coverage: str
    collection_interval_seconds: int | None
    adapter_key: str | None
    upstream_lineage: str
    adapter_implemented: bool
    selected: bool
    credentials_configured: bool
    credential_variables: tuple[str, ...]
    access_requirement: str
    state: Literal['not_implemented','not_configured','disabled','never_collected','incomplete',
        'success','failure','parser_failure']
    operational: Operational | None


class IngestionResponse(Contract):
    generated_at: datetime
    production_promotion: Literal[False] = False
    phase_complete: Literal[False] = False
    items: list[ProviderView]


async def read(db, settings, now):
    async def operation(c):
        await db._check(c)
        rows = (await c.execute(text("""SELECT s.key,s.enabled,p.lease_until,p.cursor_updated_at,
            b.next_allowed_at,b.consecutive_failures,r.status,r.incomplete,r.records_accepted,r.error_code,
            r.completed_at,r.provider_updated_at,
            (SELECT count(*) FROM raw_observations o WHERE o.source_id=s.id) AS raw_identities,
            (SELECT count(*) FROM normalized_observations n JOIN raw_observations o
                ON o.id=n.raw_observation_id WHERE o.source_id=s.id) AS historical_assertions
            FROM sources s LEFT JOIN source_poll_state p ON p.source_id=s.id
            LEFT JOIN source_backoff b ON b.source_id=s.id
            LEFT JOIN LATERAL(SELECT * FROM source_runs WHERE source_id=s.id
                ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
            WHERE s.key=ANY(CAST(:keys AS text[]))"""),
            dict(keys=[p.key for p in PROVIDERS]))).mappings()
        by_key = {r['key']: dict(r) for r in rows}
        items = []
        for p in PROVIDERS:
            adapter_key=p.adapter or p.key
            implemented = adapter_key in CONTRACTS
            ready = configured(p, settings.provider_secrets)
            selected = settings.live_sources and (p.key in settings.source_keys or adapter_key in settings.source_keys)
            row = by_key.get(adapter_key)
            state = ('not_implemented' if not implemented else 'not_configured' if not ready
                else 'disabled' if not selected or (row and not row['enabled']) else 'never_collected' if not row or not row['status']
                else 'incomplete' if row['incomplete'] else row['status'])
            items.append(dict(key=p.key, provider=p.name, batch=p.batch, kind=p.kind,
                adapter_implemented=implemented, selected=selected, credentials_configured=ready,
                measurements=p.measurements,evidence_kind=p.evidence_kind,ranked_priority=p.ranked_priority,
                retention_policy=CONTRACTS[adapter_key].retention if implemented else p.retention,
                historical_coverage=p.historical_coverage,
                collection_interval_seconds=CONTRACTS[adapter_key].polling_seconds if implemented else None,
                adapter_key=adapter_key if implemented else None,
                upstream_lineage=p.upstream_lineage,
                credential_variables=p.credentials, access_requirement=p.access,
                state=state, operational=row))
        return dict(generated_at=now, production_promotion=False, phase_complete=False,
            items=items)
    return await db.pattern_transaction(operation)
