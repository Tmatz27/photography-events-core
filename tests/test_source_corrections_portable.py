from dataclasses import replace
from datetime import timedelta

import pytest

from pec.sources.contracts import INATURALIST, NWS
from pec.sources.storage import future_update
from pec.sources import backoff
from pec.scheduler import State
from test_source_contracts import NOW, forecast
from pec.sources import nws


def test_contract_clock_tolerance_configurable_not_forecast_valid_time():
    contract = replace(INATURALIST, provider_clock_skew_seconds=60)
    assert future_update(contract, NOW + timedelta(seconds=61), NOW)
    assert not future_update(contract, NOW + timedelta(seconds=60), NOW)
    fact = nws.forecast(
        forecast(
            startTime=(NOW + timedelta(days=3)).isoformat(), endTime=(NOW + timedelta(days=4)).isoformat()
        ),
        NOW,
    )
    assert not future_update(NWS, fact.provider_updated_at, NOW)
    with pytest.raises(ValueError):
        replace(contract, provider_clock_skew_seconds=-1)


async def test_f3_backoff_routes_to_shadow_pool_only():
    class Result:
        def mappings(self):
            return self

        def first(self):
            return None

        def scalar_one(self):
            return 1

    class Connection:
        async def execute(self, *args, **kwargs):
            return Result()

    class DB:
        writes = []

        async def transaction(self, *args, **kwargs):
            raise AssertionError("production pool used")

        async def pattern_transaction(self, operation, **kwargs):
            self.writes.append(kwargs.get("write", False))
            return await operation(Connection())

    db = DB()
    assert await backoff.load(db, "inaturalist", NOW) == State(NOW)
    await backoff.save(db, "inaturalist", State(NOW))
    assert db.writes == [False, True]
