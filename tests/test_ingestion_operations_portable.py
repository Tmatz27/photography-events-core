"""Approved inventory and actual asynchronous socket resource bounds."""
import asyncio
from dataclasses import replace
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

from pec.config import Settings
from pec.sources.http import FetchError, read
from pec.sources.inventory import INVENTORY, CREDENTIAL_NAMES, selection, configured
from test_api import SETTINGS


def test_entire_approved_scope_is_retained_in_inventory():
    assert set(INVENTORY) >= {'inaturalist','nws_live_context','wfigs_current','ebird_notable','ebird_species',
        'birdcast','nexrad','usfws_counts','usfws_reports','condor_express','field_reports','ndbc','cdip_models','cdip_measured','coops_predictions','calhabmap',
        'coastwatch_sst','coastwatch_chlorophyll','coastwatch_upwelling','mbari_ocean_song','king_tides','grunion','open_meteo','open_meteo_air_quality',
        'sunsetwx','ovation','goes18','hpwren','usgs_water','cdec','nwps','nps','caltrans','sentinel2',
        'theodore_payne','desertusa','california_fall_color','seasonal_references','nasa_eclipses',
        'meteor_reference','astronomical_inputs','email_reports','legacy_seasonal_references','motus','whale_alert',
        'whale_safe','blm','county_air_quality','cdec_river','cdec_rainfall','cdec_snow','cdec_soil_moisture',
        'landsat','purpleair','cal_fire','watchduty','state_parks_gis','usfs_access','beach_restrictions',
        'goes_glm','audubon_reports','ranger_reports','harbor_operator_reports','approved_rss',
        'nws_active_alerts','nws_gridpoints','nws_hourly_forecast','nws_forecast_discussions',
        'inaturalist_plants','xerces_monarch','state_parks_monarch','elephant_seal_reports','harbor_seal_reports'}
    assert all(p.batch in range(1,6) for p in INVENTORY.values())
    assert all(p.kind=='reference' for p in (INVENTORY['nasa_eclipses'],INVENTORY['meteor_reference'],INVENTORY['king_tides']))
    assert {p.ranked_priority for p in INVENTORY.values() if p.ranked_priority}==set(range(1,21))


def test_unimplemented_credentials_are_not_integration_claims_and_secrets_are_redacted():
    provider = INVENTORY['ebird_notable']
    assert not configured(provider,{})
    settings = replace(SETTINGS,provider_secrets={'CORE_EBIRD_API_KEY':'private-test-secret'})
    assert configured(provider,settings.provider_secrets)
    assert 'private-test-secret' not in repr(settings)
    assert configured(INVENTORY['ndbc'],{})
    with pytest.raises(ValueError,match='Unknown provider credential'):
        replace(SETTINGS,provider_secrets={'arbitrary':'private-test-secret'})


def test_env_and_compose_describe_every_committed_credential():
    root=Path(__file__).resolve().parents[1]
    for name in CREDENTIAL_NAMES:
        assert name+'=' in (root/'.env.example').read_text()
        assert name+':' in (root/'compose.yaml').read_text()


def test_selection_and_environment_do_not_echo_unknown_secrets(monkeypatch):
    assert set(selection('all'))==set(INVENTORY)
    assert selection('inaturalist,nws_live_context')==('inaturalist','nws_live_context')
    for value in ('inaturalist,inaturalist','secret_unknown_key'):
        with pytest.raises(ValueError) as exc:
            selection(value)
        assert value not in str(exc.value)
    monkeypatch.setenv('CORE_DATABASE_URL',str(SETTINGS.database_url))
    monkeypatch.setenv('CORE_API_TOKEN',SETTINGS.api_token)
    monkeypatch.setenv('CORE_EBIRD_API_KEY','private-env-secret')
    assert Settings.from_env().provider_secrets['CORE_EBIRD_API_KEY']=='private-env-secret'
    assert 'private-env-secret' not in repr(Settings.from_env())


async def serve(handler):
    app=web.Application()
    app.router.add_get('/data',handler)
    runner=web.AppRunner(app,shutdown_timeout=0.1)
    await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    port=site._server.sockets[0].getsockname()[1]
    return runner,f'http://127.0.0.1:{port}/data'


async def test_real_http_cancellation_closes_socket_without_background_thread():
    started=asyncio.Event()
    connection=[]
    async def blocked(request):
        connection.append(request.transport)
        response=web.StreamResponse()
        await response.prepare(request)
        await response.write(b'{')
        started.set()
        await asyncio.Event().wait()
    runner,url=await serve(blocked)
    try:
        async with aiohttp.ClientSession() as session:
            task=asyncio.create_task(read(url,'PhotographyEventsCore-test',session=session))
            await asyncio.wait_for(started.wait(),1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task,1)
            for _ in range(20):
                if connection[0].is_closing():
                    break
                await asyncio.sleep(0.01)
            assert connection[0].is_closing()
    finally:
        await runner.cleanup()


@pytest.mark.parametrize('kind',['oversized','bad_json','redirect','rate_limit'])
async def test_real_stream_size_json_redirect_and_retry_bounds(kind):
    calls=[]
    async def response(request):
        calls.append(request.path)
        if kind=='redirect':
            return web.Response(status=302,headers={'Location':'http://127.0.0.1:1/private'})
        if kind=='rate_limit':
            return web.Response(status=429,headers={'Retry-After':'3600'},text='secret-body')
        return web.Response(body=b'x'*(16*1024*1024+1) if kind=='oversized' else b'{secret-body')
    runner,url=await serve(response)
    try:
        async with aiohttp.ClientSession() as session:
            if kind in ('oversized','bad_json'):
                with pytest.raises(FetchError) as exc:
                    await read(url,'PhotographyEventsCore-test',session=session)
                assert exc.value.code==('response_too_large' if kind=='oversized' else 'invalid_json')
                assert 'secret-body' not in str(exc.value)
            else:
                result=await read(url,'PhotographyEventsCore-test',session=session)
                assert result.body=={} and result.status==(302 if kind=='redirect' else 429)
                assert result.retry_after==('3600' if kind=='rate_limit' else None)
        assert len(calls)==1
    finally:
        await runner.cleanup()
