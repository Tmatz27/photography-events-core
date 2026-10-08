"""PRODUCT POLICY UNDER CALIBRATION: no ecological or production thresholds."""

from dataclasses import asdict, dataclass

from ..patterns.policy import Destination, Policy, POLICIES
from .contracts import BOUNDS, PISMO


@dataclass(frozen=True)
class CalibrationPolicy(Policy):
    calibration_only: bool = True


POLICIES_SHADOW = tuple(
    CalibrationPolicy(
        **{
            **asdict(policy),
            "version": "m3a-calibration-1",
            "compatibility_key": "m3a-calibration-1",
            "operating_bounds": BOUNDS,
            "destinations": (
                (
                    Destination(
                        PISMO["key"],
                        PISMO["name"],
                        PISMO["latitude"],
                        PISMO["longitude"],
                        PISMO["association_meters"],
                    ),
                )
                if policy.key == "monarch_aggregation"
                else ()
            ),
        }
    )
    for policy in POLICIES
    if policy.key in ("black_bear_activity", "monarch_aggregation")
)


def condition(temperature):
    if temperature is None:
        return "unknown"
    return (
        "Cool forecast: resting/clustered photography may be favored; grove microclimate and aggregation unconfirmed."
        if temperature <= 55
        else "Warmer forecast: flying/basking photography may be favored; presence is not invalidated."
    )
