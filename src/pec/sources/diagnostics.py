"""Ingestion inventory diagnostics: counts/status only, no provider secrets or coordinates."""
from datetime import datetime
from typing import Literal
from pydantic import Field

from sqlalchemy import text

from ..schemas import Contract

from .contracts import CONTRACTS
from .inventory import PROVIDERS, configured
from .environment_contracts import effective_contract
from .environment_health import coverage, history_health


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
    records_received: int | None = None
    records_rejected: int | None = None
    requests: int | None = None
    last_success_at: datetime | None = None
    history_complete: bool = False
    native_evidence_asof: datetime | None = None


class EnvironmentalDataset(Contract):
    quantity: str
    evidence_kind: str
    historical_assertions: int
    current_numeric_values: int
    current_withdrawals: int
    native_as_of: datetime | None
    last_received_at: datetime | None
    native_freshness: Literal['current','stale','unknown']


class StationOutcome(Contract):
    station: str
    window_start: datetime
    window_end: datetime
    request_complete: bool
    requests: int
    successful_requests: int
    received: int
    parsed: int
    rejected: int
    measurement_asof: datetime | None
    forecast_asof: datetime | None
    measurement_values: int
    forecast_values: int
    error_code: str | None
    outcome: str
    state: str
    measurement_freshness: str
    forecast_freshness: str


class StationCoverage(Contract):
    mode: Literal['current','historical']
    configured_stations: int
    successful_requests: int
    successful_stations: int
    states: dict[str,int]
    stations: list[StationOutcome]
    measurement_freshness: str
    forecast_freshness: str


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
    authentication_status: Literal['not_required','configured','credentials_needed','access_pending']
    credential_variables: tuple[str, ...]
    access_requirement: str
    state: Literal['not_implemented','not_configured','disabled','never_collected','incomplete',
        'success','failure','parser_failure']
    operational: Operational | None
    history_operational: Operational | None = None
    native_freshness: Literal['current','stale','unknown'] = 'unknown'
    datasets: list[EnvironmentalDataset] = Field(default_factory=list)
    coverage: StationCoverage | None = None
    history_coverage: StationCoverage | None = None
    history_worker_health: Literal['current','stale','unknown'] = 'unknown'


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
            r.records_received,r.records_rejected,r.requests,
            (SELECT max(completed_at) FROM source_runs WHERE source_id=s.id AND status='success') AS last_success_at,
            COALESCE((p.checkpoint->>'complete')::boolean,FALSE) AS history_complete,
            r.completed_at,r.provider_updated_at,r.native_evidence_asof,r.context_payload,
            (SELECT count(*) FROM raw_observations o WHERE o.source_id=s.id) AS raw_identities,
            (SELECT count(*) FROM normalized_observations n JOIN raw_observations o
                ON o.id=n.raw_observation_id WHERE o.source_id=s.id)+
            (SELECT count(*) FROM environmental_assertions e JOIN raw_observations o ON o.id=e.raw_observation_id
                WHERE o.source_id=s.id OR e.source_run_id IN (SELECT id FROM source_runs WHERE source_id=s.id)) AS historical_assertions
            FROM sources s LEFT JOIN source_poll_state p ON p.source_id=s.id
            LEFT JOIN source_backoff b ON b.source_id=s.id
            LEFT JOIN LATERAL(SELECT * FROM source_runs WHERE source_id=s.id
                ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
            WHERE s.key=ANY(CAST(:keys AS text[]))"""),
            dict(keys=[p.key for p in PROVIDERS]+[p.key+'_history' for p in PROVIDERS]))).mappings()
        by_key = {r['key']: dict(r) for r in rows}
        contexts = {key:(row.pop('context_payload') or {}).get('environment') for key,row in by_key.items()}
        items = []
        for p in PROVIDERS:
            adapter_key=p.adapter or p.key
            implemented = adapter_key in CONTRACTS
            contract=effective_contract(CONTRACTS[adapter_key],settings.collection_scope) if implemented else None
            ready = configured(p, settings.provider_secrets)
            selected = settings.live_sources and (p.key in settings.source_keys or adapter_key in settings.source_keys)
            row = by_key.get(adapter_key)
            from .debug import freshness
            datasets=[]
            if implemented:
                values=(await c.execute(text("""SELECT quantity,evidence_kind,count(*) AS historical_assertions,
                    count(*) FILTER(WHERE superseded_at IS NULL AND NOT withdrawn AND numeric_value IS NOT NULL) AS current_numeric_values,
                    count(*) FILTER(WHERE superseded_at IS NULL AND withdrawn) AS current_withdrawals,
                    max(CASE WHEN evidence_kind='measurement' THEN valid_at
                        WHEN evidence_kind='forecast' THEN issued_at ELSE provider_updated_at END)
                        FILTER(WHERE superseded_at IS NULL AND NOT withdrawn) AS native_as_of,
                    max(last_received_at) AS last_received_at FROM environmental_assertions
                    WHERE dataset_key=:key GROUP BY quantity,evidence_kind ORDER BY quantity,evidence_kind"""),
                    dict(key=adapter_key))).mappings()
                for value in values:
                    item=dict(value)
                    item['native_freshness']=freshness(CONTRACTS[adapter_key],
                        {**(row or {}),'provider_updated_at':item['native_as_of'],'native_evidence_asof':item['native_as_of'],
                            'completed_at':item['last_received_at']},now) if row else 'unknown'
                    datasets.append(item)
            state = ('not_implemented' if not implemented else 'not_configured' if not ready
                else 'disabled' if not selected or (row and not row['enabled']) else 'never_collected' if not row or not row['status']
                else 'incomplete' if row['incomplete'] else row['status'])
            items.append(dict(key=p.key, provider=p.name, batch=p.batch, kind=p.kind,
                adapter_implemented=implemented, selected=selected, credentials_configured=ready,
                authentication_status=('configured' if ready else 'credentials_needed') if p.credentials
                    else 'not_required' if p.access=='public' else 'access_pending',
                measurements=p.measurements,evidence_kind=p.evidence_kind,ranked_priority=p.ranked_priority,
                retention_policy=CONTRACTS[adapter_key].retention if implemented else p.retention,
                historical_coverage=p.historical_coverage,
                collection_interval_seconds=contract.polling_seconds if implemented else None,
                adapter_key=adapter_key if implemented else None,
                upstream_lineage=p.upstream_lineage,
                credential_variables=p.credentials, access_requirement=p.access,
                state=state, operational=row,history_operational=by_key.get(adapter_key+'_history'),
                native_freshness=freshness(contract,row,now) if implemented else 'unknown',datasets=datasets,
                coverage=coverage(contexts.get(adapter_key),now,contract) if implemented else None,
                history_coverage=coverage(contexts.get(adapter_key+'_history'),now,contract) if implemented else None,
                history_worker_health=history_health(by_key.get(adapter_key+'_history'),now,3600)))
        return dict(generated_at=now, production_promotion=False, phase_complete=False,
            items=items)
    return await db.pattern_transaction(operation)
