"""L1: one damaged stored metadata envelope cannot reject unrelated assertions."""
from datetime import UTC, datetime

import pytest

from pec.patterns.identity import WorkingSet, details_for, valid_details


def row(payload=None,**changes):
    return dict(id=1,raw_observation_id=17,source_key="fixture_observations",external_id=None,
        subject_key="Ursus americanus",raw_payload=payload,behavior=None,
        coordinate_uncertainty_meters=10,spatial_precision="point",credible=True,
        behaviors=["presence"],link_basis=None,observed_at=datetime(2026,10,7,tzinfo=UTC),**changes)


@pytest.mark.parametrize("payload",[None,{}, {"external_id":None},{"external_id":""}])
def test_l1_legacy_null_identity_uses_existing_raw_fallback(payload):
    assert details_for(row(payload))["origin"]=="legacy-raw-17"


@pytest.mark.parametrize("payload",[
    {"external_id":"valid","origin_namespace":"untrusted","origin_external_id":"bad"},
    {"external_id":["bad"]},
    {"external_id":"valid","coordinate_uncertainty_meters":-1},
    {"external_id":"valid","credible":"yes"},
    {"external_id":"valid","behaviors":[{}]},
    ["not a mapping"],
])
def test_l1_malformed_identity_or_metadata_is_record_isolated(payload,caplog):
    result=WorkingSet()
    bad=row(payload)
    good={**row({"external_id":"good"}),"id":2}
    assert valid_details([bad,good],result)==[good]
    assert result.invalid_ids=={1}
    assert '"event": "identity_invalid"' in caplog.text
    assert "untrusted" not in caplog.text and "coordinate_uncertainty" not in caplog.text


def test_l1_one_bad_row_among_many_good_survives():
    values=[{**row({"external_id":f"valid-{i}"}),"id":i} for i in range(200)]
    values[57]["raw_payload"]={"external_id":["invalid"]}
    result=WorkingSet()
    assert len(valid_details(values,result))==199
    assert result.invalid_ids=={57}
