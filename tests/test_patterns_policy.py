"""Policy/admission validation independent of a database; persistence tests are separate."""
import random
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from pec.config import Settings
from pec.patterns.clustering import admit, representative
from pec.patterns.identity import metadata
from pec.patterns.policy import POLICIES, behavior_codes, canonical_hash
from test_api import SETTINGS, NOW

POLICY = POLICIES[1]


def test_policy_hash_ignores_dictionary_key_order():
    policy=asdict(POLICY)
    expected=POLICY.hash
    for seed in range(30):
        items=list(policy.items())
        random.Random(seed).shuffle(items)
        assert canonical_hash(dict(items))==expected


def test_policy_change_changes_provenance():
    assert replace(POLICY,eps_meters=POLICY.eps_meters+1).hash!=POLICY.hash
    assert replace(POLICY,version="fixture-2").hash!=POLICY.hash


@pytest.mark.parametrize("changes",[{"eps_meters":float("nan")},{"eps_meters":float("inf")},
    {"min_independent_reports":0},{"clustering_crs":4326},{"clustering_crs":3857},
    {"future_tolerance_seconds":3601},{"behaviors":("made_up",)},
    {"trigger":"FORECAST_PLUS_CONFIRMATION"},{"trigger":"LIVE_CONFIRMATION_REQUIRED"},{"trigger":"COUNT_THRESHOLD"},
    {"coherence_action":"recursive"}])
def test_invalid_or_reserved_policy_cannot_run(changes):
    with pytest.raises(ValueError):
        replace(POLICY,**changes)


def test_unknown_behavior_is_not_inferred():
    assert behavior_codes({})==["presence"]
    assert behavior_codes({"behavior":"possibly cub habitat"})==["presence"]
    assert behavior_codes({"behaviors":["lunge feeding","breaching"]})==["breaching","lunge_feeding","presence"]


@pytest.mark.parametrize("changes",[{"origin_namespace":"random_live_provider","origin_external_id":"1"},
    {"origin_namespace":"fixture_observations"},{"origin_external_id":"1"},
    {"coordinate_uncertainty_meters":float("nan")},{"coordinate_uncertainty_meters":-1},
    {"behaviors":"fishing"},{"spatial_precision":"invented"},{"credible":"yes"}])
def test_untrusted_identity_or_invalid_precision_rejected(changes):
    with pytest.raises(ValueError):
        metadata({"external_id":"test",**changes},"fixture_observations")


def test_namespace_is_part_of_report_identity():
    first=metadata({"external_id":"123"},"fixture_observations")
    mirror=metadata({"external_id":"123"},"fixture_mirror_a")
    assert (first["namespace"],first["origin"])!=(mirror["namespace"],mirror["origin"])


def test_missing_precision_remains_unknown():
    row=metadata({"external_id":"test"},"fixture_observations")
    assert row["uncertainty"] is None and row["precision"]=="unknown"


def test_canonical_origin_is_preferred_to_mirror_geometry():
    base=dict(source_key="fixture_observations",origin_namespace="fixture_observations",
              external_id="123",subject_key=POLICY.subject,coordinate_uncertainty_meters=20,observed_at=NOW)
    mirror={**base,"source_key":"fixture_mirror_a","coordinate_uncertainty_meters":1}
    assert representative([mirror,base])==base


def test_temporal_precision_credibility_admission():
    base=dict(id=1,subject_key=POLICY.subject,enabled=True,observed_at=NOW,
        valid_until=NOW+timedelta(days=14),spatial_precision="point",coordinate_uncertainty_meters=10,
        latitude=35.3,longitude=-120.5,report_key="one",credible=True)
    future={**base,"id":2,"observed_at":NOW+timedelta(hours=2)}
    broad={**base,"id":3,"coordinate_uncertainty_meters":15000}
    groups,dispositions=admit([base,future,broad],POLICY,NOW)
    assert list(groups)==["one"] and dispositions=={1:"noise",2:"excluded_time",3:"regional"}
    groups,_=admit([future],POLICY,NOW+timedelta(hours=1))
    assert groups


def test_patterns_are_off_by_default_and_production_promotion_is_rejected():
    assert SETTINGS.patterns_mode=="off"
    with pytest.raises(ValueError):
        Settings(SETTINGS.database_url,SETTINGS.api_token,patterns_mode="production")
