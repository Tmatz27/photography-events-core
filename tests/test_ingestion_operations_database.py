"""Real PostgreSQL ownership, checkpoints, lifecycle and retention invariants."""
import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import text

from pec.retention import sweep
from pec.sources import backoff, inaturalist
from pec.sources.contracts import INATURALIST, NWS, WFIGS
from pec.sources.diagnostics import IngestionResponse, read
from pec.sources.models import Batch
from pec.sources.ownership import claim, release, collect_owned
from pec.sources.storage import collect, persist
from test_api import SETTINGS
from test_database import NOW
from test_patterns_database import db as database_fixture, sql, pytestmark as database_marks
from test_source_contracts import observation, alert, client
from test_source_corrections import poll, current

db=database_fixture
pytestmark=database_marks


async def test_concurrent_process_claims_have_single_owner_and_no_pool_held(db):
    claims=await asyncio.gather(*(claim(db,INATURALIST,NOW) for _ in range(8)))
    leases=[v for v in claims if v]
    assert len(leases)==1
    assert db.pattern_engine.pool.checkedout()==0 and db.engine.pool.checkedout()==0
    state=await backoff.load(db,'inaturalist',NOW)
    assert state.consecutive_failures==1 and state.next_allowed_at==NOW+timedelta(seconds=1800)
    # Restart load respects reservation even when no attempt was persisted.
    assert await claim(db,INATURALIST,NOW+timedelta(seconds=1000)) is None
    await release(db,INATURALIST,leases[0])
    assert await claim(db,INATURALIST,NOW+timedelta(seconds=1800)) is not None


async def test_expired_owner_cannot_mutate_or_release_new_owner(db):
    first=await claim(db,INATURALIST,NOW)
    later=NOW+timedelta(seconds=1801)
    second=await claim(db,INATURALIST,later)
    assert second and second.token!=first.token
    batch=Batch(snapshot=True,provider_updated_at=NOW,checkpoint={'page':9})
    batch.parse([observation()],inaturalist.parse)
    await persist(db,INATURALIST,batch,NOW,later,lease=first)
    assert not batch.complete and not await current(db)
    await release(db,INATURALIST,first)
    state=(await sql(db,'SELECT * FROM source_poll_state'))[0]
    assert state['lease_token']==second.token and state['cursor_updated_at'] is None and state['checkpoint']=={}
    run=(await sql(db,'SELECT * FROM source_runs'))[0]
    assert run['status']=='failure' and run['error_code']=='collection_lease_lost'


async def test_disabled_source_cannot_be_claimed(db):
    lease=await claim(db,WFIGS,NOW)
    await release(db,WFIGS,lease)
    async with db.engine.begin() as c:
        await c.execute(text("UPDATE sources SET enabled=FALSE WHERE key='wfigs_current'"))
    assert await claim(db,WFIGS,NOW+timedelta(hours=1)) is None


@pytest.mark.parametrize('mode',['incomplete','out_of_order','expired','too_large','complete'])
async def test_checkpoint_only_advances_with_valid_complete_owned_poll(db,mode):
    lease=await claim(db,INATURALIST,NOW)
    batch=Batch(complete=mode!='incomplete',checkpoint={'cursor':'native-cursor'} if mode!='too_large' else {'cursor':'x'*17000})
    if mode=='out_of_order':
        await persist(db,INATURALIST,Batch(),NOW+timedelta(seconds=1),NOW+timedelta(seconds=1))
    end=lease.until+timedelta(seconds=1) if mode=='expired' else NOW+timedelta(seconds=2)
    await persist(db,INATURALIST,batch,NOW,end,lease=lease)
    state=(await sql(db,'SELECT * FROM source_poll_state'))[0]
    assert state['checkpoint']==({'cursor':'native-cursor'} if mode=='complete' else {})
    assert batch.complete==(mode=='complete')


async def test_owned_cancellation_records_failure_releases_lease_and_keeps_backoff(db):
    begun=asyncio.Event()
    async def blocked(url,ua):
        begun.set()
        await asyncio.Event().wait()
    from pec.sources.http import Client
    async def noop():
        pass
    transport=Client(INATURALIST,'PhotographyEventsCore-test',reserve=noop,transport=blocked)
    task=asyncio.create_task(collect_owned(db,INATURALIST,'PhotographyEventsCore-test',client=transport,clock=lambda:NOW))
    await asyncio.wait_for(begun.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    run=(await sql(db,'SELECT * FROM source_runs'))[0]
    assert run['error_code']=='collection_cancelled' and run['status']=='failure'
    state=(await sql(db,'SELECT * FROM source_poll_state'))[0]
    assert state['lease_token'] is None and state['cursor_updated_at'] is None
    assert (await backoff.load(db,'inaturalist',NOW)).next_allowed_at>NOW


async def test_unexpected_transport_failure_is_persisted_without_secret_exception(db,caplog):
    from pec.sources.http import Client
    async def failed(url,ua):
        raise RuntimeError('private-provider-token')
    async def noop():
        pass
    transport=Client(INATURALIST,'PhotographyEventsCore-test',reserve=noop,transport=failed)
    status,_=await collect(db,INATURALIST,'PhotographyEventsCore-test',client=transport,clock=lambda:NOW)
    assert status==502
    row=(await sql(db,'SELECT * FROM source_runs'))[0]
    assert row['error_code']=='collection_adapter_failure' and row['status']=='failure'
    assert 'private-provider-token' not in caplog.text


async def test_retired_inaturalist_id_is_refreshed_and_reinstated_without_new_search_hit(db):
    record=observation()
    await poll(db,INATURALIST,[record])
    await poll(db,INATURALIST,minute=1,unavailable=[record['uuid']])
    assert not await current(db)
    transport,calls=client(INATURALIST,[{'results':[],'total_results':0}, {'results':[record],'total_results':1}])
    status,_=await collect(db,INATURALIST,'PhotographyEventsCore-test',client=transport,clock=lambda:NOW+timedelta(minutes=2))
    assert status==200 and len(calls)==2 and 'id=1' in calls[-1][0]
    assert len(await current(db))==1 and (await current(db))[0]['sensitive']
    run=(await sql(db,'SELECT * FROM source_runs ORDER BY id'))[-1]
    assert run['reinstated']==1


async def test_cap_index_survives_payload_retention_and_allows_newer_reference(db):
    await poll(db,NWS,[alert()])
    await poll(db,NWS,[alert(2,messageType='Cancel',sent=(NOW+timedelta(minutes=1)).isoformat(),
        references=[{'identifier':'urn:test:1'}])],1)
    before=await sql(db,'SELECT * FROM source_reference_barriers')
    assert len(before)==1
    await db.pattern_transaction(lambda c:sweep(c,NOW+timedelta(days=200)),write=True)
    assert (await sql(db,"SELECT raw_payload FROM raw_observations WHERE external_id='urn:test:2'"))[0]['raw_payload'] is None
    assert await sql(db,'SELECT * FROM source_reference_barriers')==before
    # Remove the per-record retirement fence to exercise retained explicit index independently.
    async with db.engine.begin() as c:
        await c.execute(text("UPDATE raw_observations SET retirement_provider_updated_at=NULL WHERE external_id='urn:test:1'"))
    replay=await poll(db,NWS,[alert()],2)
    assert replay.skipped==[('urn:test:1','stale_reference_replay')] and not await current(db)


async def test_old_native_edit_fresh_receipt_does_not_prune_live_payload_or_history(db):
    from test_h1_safety import old_fire, receipt
    await receipt(db,[old_fire()],0)
    before=await sql(db,'SELECT * FROM normalized_observations')
    await db.pattern_transaction(lambda c:sweep(c,NOW+timedelta(days=80)),write=True)
    assert (await sql(db,'SELECT raw_payload FROM raw_observations'))[0]['raw_payload'] is not None
    assert await sql(db,'SELECT * FROM normalized_observations')==before


async def test_full_inventory_diagnostics_are_honest_and_do_not_expose_coordinates_or_credentials(db):
    await poll(db,INATURALIST,[observation()])
    settings=replace(SETTINGS,patterns_mode='shadow',live_sources=True,
        provider_secrets={'CORE_EBIRD_API_KEY':'private-test-secret'})
    result=IngestionResponse(**await read(db,settings,NOW))
    items={p.key:p for p in result.items}
    assert items['inaturalist'].operational.historical_assertions==1
    assert items['ebird_notable'].credentials_configured and items['ebird_notable'].state=='not_implemented'
    assert not items['mbari_ocean_song'].credentials_configured
    data=result.model_dump_json()
    assert 'private-test-secret' not in data and 'geojson' not in data and 'external_id' not in data
    assert not result.phase_complete and not result.production_promotion
