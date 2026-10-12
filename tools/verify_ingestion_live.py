"""Bounded genuine provider collection plus database verification; never seed fixtures.

Run explicitly against a migrated disposable *_test database or use --operator
for an authorized Unraid collection. No raw identities/coordinates/secrets are
written to the receipt. Provider outages are recorded, not manufactured successes.
"""
import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from pec.config import Settings
from pec.database import Database
from pec.sources.contracts import CONTRACTS
from pec.sources import backoff
from pec.sources.ownership import collect_owned
from pec.scheduler import next_state


async def run(args):
    settings=Settings.from_env()
    name=make_url(settings.database_url).database
    if not args.operator and not name.endswith('_test'):
        raise ValueError('Use a disposable *_test database or explicitly select --operator')
    keys=tuple(args.sources.split(','))
    if not keys or len(set(keys))!=len(keys) or any(key not in CONTRACTS for key in keys):
        raise ValueError('Live verification requires implemented source contracts')
    db=Database(settings)
    receipt={'started_at':datetime.now(UTC).isoformat(),'genuine_network':True,
        'mode':'operator' if args.operator else 'disposable_postgis',
        'production_promotion':False,'items':[]}
    try:
        await db.ready()
        for key in keys:
            started=datetime.now(UTC)
            previous=await backoff.load(db,key,started)
            retry=None
            code='verification_failed'
            try:
                async with asyncio.timeout(CONTRACTS[key].scheduler_policy.timeout):
                    status,retry=await collect_owned(db,CONTRACTS[key],settings.source_user_agent)
                code=None
            except TimeoutError:
                status=503
                code='verification_timeout'
            except Exception:
                status=503
            async def inspect(c):
                row=(await c.execute(text("""SELECT r.status,r.incomplete,r.error_code,r.records_received,
                    r.records_accepted,r.records_rejected,r.requests,r.bytes_received,r.corrections,r.duplicates,
                    r.provider_updated_at,r.completed_at,r.content_sha256,p.cursor_updated_at,
                    (SELECT count(*) FROM raw_observations WHERE source_id=s.id) AS persisted_identities,
                    (SELECT count(*) FROM normalized_observations n JOIN raw_observations o
                        ON o.id=n.raw_observation_id WHERE o.source_id=s.id) AS persisted_assertions,
                    (SELECT count(*) FROM raw_observations WHERE source_id=s.id
                        AND fetched_at>=:started AND provider_updated_at IS NOT NULL AND content_sha256 IS NOT NULL) AS verified_receipts
                    FROM sources s JOIN source_poll_state p ON p.source_id=s.id
                    LEFT JOIN LATERAL(SELECT * FROM source_runs WHERE source_id=s.id
                        AND started_at>=:started ORDER BY id DESC LIMIT 1) r ON TRUE WHERE s.key=:key"""),
                    dict(key=key,started=started))).mappings().first()
                return dict(row) if row else {}
            row=await db.pattern_transaction(inspect)
            if row.get('status'):
                await backoff.save(db,key,next_state(CONTRACTS[key].scheduler_policy,previous,datetime.now(UTC),
                    success=200<=status<300,retry_after=retry))
            verified=bool(row.get('verified_receipts',0)>0)
            item=dict(source=key,http_outcome=status,verification_error=code,
                live_collection_verified=bool(status==200 and row.get('status')=='success' and not row.get('incomplete')),
                persistence_verified=verified,database=row)
            receipt['items'].append(item)
    finally:
        receipt['completed_at']=datetime.now(UTC).isoformat()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(receipt,default=lambda v:v.isoformat(),indent=2)+'\n')
        await db.close()
    print(json.dumps(receipt,default=lambda v:v.isoformat(),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',default='inaturalist,wfigs_current,nws_live_context')
    parser.add_argument('--output',type=Path,default=Path('/tmp/ingestion-live.json'))
    parser.add_argument('--operator',action='store_true')
    asyncio.run(run(parser.parse_args()))


if __name__=='__main__':
    main()
