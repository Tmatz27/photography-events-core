"""Explicit authenticated projections; no raw provider body, IDs or points."""
from dataclasses import asdict
from datetime import timedelta
from datetime import datetime
from typing import Literal

from pydantic import Field

from sqlalchemy import text

from .contracts import CONTRACTS, PISMO
from .calibration import condition
from .contracts import SourceContract
from ..schemas import Contract


class Volume(Contract):
    requests: int
    received: int
    accepted: int
    rejected: int
    bytes: int
    corrections: int
    duplicates: int
    obscured: int
    private: int
    rate_limits: int
    unique_records: int
    obscured_percentage: float | None
    private_percentage: float | None


class Operational(Contract):
    status: str
    provider_updated_at: datetime | None
    records_received: int
    records_accepted: int
    records_rejected: int
    parser_error_counts: dict[str,int]
    error_code: str | None
    incomplete: bool
    latency_ms: int
    next_allowed_at: datetime | None
    consecutive_failures: int | None
    last_successful_fetch: datetime | None
    requests_reserved_today: int
    alert_native_asof: str | None


class ContractView(Contract):
    contract: SourceContract
    contract_hash: str
    freshness: Literal['current','stale','unknown']
    operational: Operational | None
    utc_day_volume: Volume


class ContractResponse(Contract):
    mode: Literal['shadow']='shadow'
    production_promotion: Literal[False]=False
    generated_at: datetime
    items: list[ContractView]


class CalibrationView(Contract):
    phenomenon_key: str
    level: Literal['none','signal','developing_watch']
    provenance_kind: Literal['CORE_INTERPRETATION']='CORE_INTERPRETATION'
    policy_basis: str
    policy_provenance: Literal['PHENOMENON_POLICY']='PHENOMENON_POLICY'
    production_eligibility: Literal[False]=False
    animal_count: None = None
    major_aggregation_confirmed: Literal[False]=False
    behavior_confirmation: Literal[False]=False
    condition: str
    safety: Literal['hold_candidate','no_intersection','unknown','not_assessed']
    destination_key: str | None


class CalibrationResponse(Contract):
    mode: Literal['off','shadow']
    production_promotion: Literal[False]=False
    pattern_analysis_state: str
    sources: dict[str,Literal['current','stale','unknown']] = Field(default_factory=dict)
    items: list[CalibrationView]
    monarch_count_confirmation: str


def freshness(contract,row,now):
    if not row or not row['enabled'] or row['status']!='success' or row['incomplete']:
        return 'unknown'
    stamp=row['provider_updated_at']
    if stamp is None:
        return 'unknown'
    return 'stale' if now-stamp>timedelta(seconds=contract.freshness_seconds) or stamp>now+timedelta(hours=1) else 'current'


async def contracts(db,now):
    async def operation(c):
        await db._check(c)
        items=[]
        for key,contract in CONTRACTS.items():
            row=(await c.execute(text("""SELECT s.enabled,r.*,b.next_allowed_at,b.consecutive_failures,
                p.requests_today,p.quota_day FROM sources s
                LEFT JOIN LATERAL(SELECT * FROM source_runs WHERE source_id=s.id ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
                LEFT JOIN source_backoff b ON b.source_id=s.id LEFT JOIN source_poll_state p ON p.source_id=s.id
                WHERE s.key=:key"""),dict(key=key))).mappings().first()
            good=(await c.execute(text("""SELECT max(r.completed_at) FROM source_runs r JOIN sources s ON s.id=r.source_id
                WHERE s.key=:key AND r.status='success'"""),dict(key=key))).scalar_one()
            volume=(await c.execute(text("""SELECT COALESCE(sum(requests),0) AS requests,COALESCE(sum(records_received),0) AS received,
                COALESCE(sum(records_accepted),0) AS accepted,COALESCE(sum(records_rejected),0) AS rejected,
                COALESCE(sum(bytes_received),0) AS bytes,COALESCE(sum(corrections),0) AS corrections,
                COALESCE(sum(duplicates),0) AS duplicates,COALESCE(sum(obscured_records),0) AS obscured,
                COALESCE(sum(private_records),0) AS private,COALESCE(sum(rate_limit_count),0) AS rate_limits
                FROM source_runs r JOIN sources s ON s.id=r.source_id WHERE s.key=:key AND r.started_at>=:day"""),
                dict(key=key,day=now.replace(hour=0,minute=0,second=0,microsecond=0)))).mappings().one()
            unique=(await c.execute(text("""SELECT count(DISTINCT eid) FROM source_runs r JOIN sources s ON s.id=r.source_id
                CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(r.context_payload->'seen_ids','[]')) eid
                WHERE s.key=:key AND r.started_at>=:day"""),dict(key=key,day=now.replace(hour=0,minute=0,second=0,microsecond=0)))).scalar_one()
            counts=dict(volume)
            counts.update(unique_records=unique,obscured_percentage=(100*volume['obscured']/volume['accepted'] if volume['accepted'] else None),
                private_percentage=(100*volume['private']/volume['accepted'] if volume['accepted'] else None))
            operational=None
            if row and row['status']:
                operational={field:row[field] for field in ('status','provider_updated_at','records_received','records_accepted','records_rejected',
                    'parser_error_counts','error_code','incomplete','latency_ms','next_allowed_at','consecutive_failures')}
                operational['last_successful_fetch']=good
                operational['requests_reserved_today']=row['requests_today'] if row['quota_day']==now.date() else 0
                operational['alert_native_asof']=(row['context_payload'] or {}).get('alert_asof')
            items.append(dict(contract=asdict(contract),contract_hash=contract.hash,freshness=freshness(contract,row,now),
                operational=operational,utc_day_volume=counts))
        return dict(mode='shadow',production_promotion=False,generated_at=now,items=items)
    return await db.pattern_transaction(operation)


async def calibration(db,now):
    from ..patterns.api import read
    patterns=await read(db,now)
    async def operation(c):
        sources={}
        for key,contract in CONTRACTS.items():
            row=(await c.execute(text("""SELECT s.enabled,r.* FROM sources s LEFT JOIN LATERAL
                (SELECT * FROM source_runs WHERE source_id=s.id ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
                WHERE s.key=:key"""),dict(key=key))).mappings().first()
            sources[key]=freshness(contract,row,now)
        presence=(await c.execute(text("""SELECT DISTINCT n.subject_key FROM normalized_observations n JOIN raw_observations r
            ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id WHERE s.key='inaturalist' AND s.enabled
            AND n.superseded_at IS NULL AND n.subject_type='species' AND n.credible AND n.valid_until>=:now
            AND ((n.observed_at BETWEEN :start AND :end) OR (n.time_precision='date' AND n.observed_date BETWEEN :date_start AND :date_end))"""),
            dict(now=now,start=now-timedelta(days=4),end=now+timedelta(hours=1),date_start=(now-timedelta(days=4)).date(),date_end=now.date()))).scalars().all()
        registry=(await c.execute(text("""SELECT sensitivity='public' AND public_geometry IS NOT NULL
            AND ST_Equals(public_geometry,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)) FROM locations WHERE key=:key"""),
            dict(key=PISMO['key'],lon=PISMO['longitude'],lat=PISMO['latitude']))).scalar_one_or_none()
        destination_valid=registry is not False
        fire=(await c.execute(text("""SELECT EXISTS(SELECT 1 FROM normalized_observations n JOIN raw_observations r
            ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id WHERE s.key='wfigs_current' AND s.enabled
            AND n.superseded_at IS NULL AND n.valid_until>=:now AND n.source_metadata->>'qualifying_current_wildfire'='true'
            AND ST_Intersects(n.analysis_area,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)))"""),
            dict(now=now,lon=PISMO['longitude'],lat=PISMO['latitude']))).scalar_one()
        temp=(await c.execute(text("""SELECT n.source_metadata FROM normalized_observations n JOIN raw_observations r
            ON r.id=n.raw_observation_id JOIN sources s ON s.id=r.source_id WHERE s.key='nws_live_context' AND s.enabled
            AND n.superseded_at IS NULL AND n.subject_type='condition' AND n.valid_until>:now
            AND (n.source_metadata->>'period_start')::timestamptz<=:now
            ORDER BY n.provider_updated_at DESC LIMIT 1"""),dict(now=now))).scalar_one_or_none()
        items=[]
        for key,subject in (('black_bear_activity','Ursus americanus'),('monarch_aggregation','Danaus plexippus')):
            active=[p for p in patterns.items if p.phenomenon_key==key and p.state!='ended' and not p.redacted
                and p.policy_version=='m3a-calibration-1' and patterns.analysis_state=='current']
            if key=='monarch_aggregation':
                active=[p for p in active if p.location and p.location.key==PISMO['key'] and destination_valid]
            level='developing_watch' if active and sources['inaturalist']=='current' else 'signal' if subject in presence else 'none'
            safety=('hold_candidate' if fire else 'no_intersection') if sources['wfigs_current']=='current' and destination_valid else 'unknown'
            weather=condition(temp.get('temperature_f') if temp and sources['nws_live_context']=='current' else None)
            items.append(dict(phenomenon_key=key,level=level,provenance_kind='CORE_INTERPRETATION',
                policy_basis='PRODUCT POLICY UNDER CALIBRATION; NOT ECOLOGICAL FACT',policy_provenance='PHENOMENON_POLICY',
                production_eligibility=False,animal_count=None,major_aggregation_confirmed=False,behavior_confirmation=False,
                condition=weather if key=='monarch_aggregation' else 'not_assessed',
                safety=safety if key=='monarch_aggregation' else 'not_assessed',
                destination_key=PISMO['key'] if active and key=='monarch_aggregation' else None))
        return dict(mode=db.patterns_mode,production_promotion=False,pattern_analysis_state=patterns.analysis_state,
            sources=sources,items=items,monarch_count_confirmation='Requires verified dated grove/count source; machine access deferred')
    return await db.pattern_transaction(operation)
