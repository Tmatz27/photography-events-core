"""Source-controlled fixture policies; numeric thresholds are NOT ecological facts."""
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

BEHAVIORS = frozenset(("presence", "feeding", "fishing", "courtship", "rut", "mating",
    "pupping", "aggregation", "migration", "roosting", "sow_with_cubs", "lunge_feeding", "breaching"))
# Only exact, explicit adapter terms are mapped. Presence never implies behavior.
ALIASES = {"lunge feeding": "lunge_feeding", "sow with cubs": "sow_with_cubs", "bugling": "rut"}
TRIGGERS = frozenset(("AGGREGATION_REQUIRED", "BEHAVIOR_REQUIRED", "COUNT_THRESHOLD",
    "EXCEPTIONAL_PRESENCE", "LIVE_CONFIRMATION_REQUIRED", "FORECAST_PLUS_CONFIRMATION"))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Destination:
    key: str
    name: str
    latitude: float
    longitude: float
    viewing_radius_meters: float
    sensitive_allowed: bool = False

    def __post_init__(self):
        import math
        if (not self.key or not self.name or not math.isfinite(self.latitude) or not math.isfinite(self.longitude)
                or not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180
                or not math.isfinite(self.viewing_radius_meters) or self.viewing_radius_meters <= 0):
            raise ValueError("Invalid approved destination")


@dataclass(frozen=True)
class Policy:
    key: str
    subject: str
    title: str
    category: Literal["mammals", "birds", "insects"]
    trigger: str = "AGGREGATION_REQUIRED"
    version: str = "fixture-1"
    compatibility_key: str = "fixture-1"
    clustering_crs: int = 3310
    eps_meters: float = 1000
    min_independent_reports: int = 2
    minimum_observations: int = 2
    temporal_window_seconds: int = 4 * 86400
    future_tolerance_seconds: int = 3600
    maximum_cluster_diameter_meters: float = 4000
    coordinate_uncertainty_limit: float = 1000
    continuation_gap_seconds: int = 2 * 86400
    episode_spatial_tolerance: float = 2000
    behaviors: tuple[str, ...] = ()
    behavior_min_reports: int = 2
    qualifying_reports: int = 5
    count_requirement: int | None = None
    allow_regional: bool = True
    allow_merge: bool = False
    coherence_action: str = "reject"
    operating_bounds: tuple[float, float, float, float] = (-125, 31, -113, 43)
    destinations: tuple[Destination, ...] = ()

    def __post_init__(self):
        if self.trigger not in TRIGGERS or self.category not in ("mammals", "birds", "insects"):
            raise ValueError("Unknown pattern policy")
        if self.trigger in ("LIVE_CONFIRMATION_REQUIRED", "FORECAST_PLUS_CONFIRMATION"):
            raise ValueError("Reserved trigger family requires a future explicit confirmation adapter")
        if self.clustering_crs != 3310 or self.coherence_action != "reject":
            raise ValueError("M2 currently validates EPSG:3310 and deterministic rejection only")
        if not set(self.behaviors) <= BEHAVIORS:
            raise ValueError("Unknown required behavior")
        import math
        positive = (self.eps_meters, self.min_independent_reports, self.minimum_observations,
            self.temporal_window_seconds, self.maximum_cluster_diameter_meters,
            self.coordinate_uncertainty_limit, self.continuation_gap_seconds, self.episode_spatial_tolerance,
            self.behavior_min_reports, self.qualifying_reports)
        if any(not math.isfinite(v) or v <= 0 for v in positive):
            raise ValueError("Pattern thresholds must be finite and positive")
        for count in (self.min_independent_reports,self.minimum_observations,self.behavior_min_reports,self.qualifying_reports):
            if type(count) is not int or count > 2147483647:
                raise ValueError("Report thresholds must be integer counts")
        if self.count_requirement is not None and (type(self.count_requirement) is not int or not 0 <= self.count_requirement <= 2147483647):
            raise ValueError("Invalid animal count requirement")
        if self.trigger == "BEHAVIOR_REQUIRED" and not self.behaviors:
            raise ValueError("A behavior gate needs explicit canonical behaviors")
        if not 0 <= self.future_tolerance_seconds <= 3600:
            raise ValueError("Invalid future tolerance")

    @property
    def hash(self):
        return canonical_hash(asdict(self))


def behavior_codes(record):
    values = record.get("behaviors", [])
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValueError("Behavior terms must be strings")
    if record.get("behavior"):
        values = [*values, record["behavior"]]
    codes = {"presence"}
    for value in values:
        code = ALIASES.get(value.strip().lower(), value.strip().lower())
        if code in BEHAVIORS:
            codes.add(code)
    return sorted(codes)


# No destination is implicitly approved. Synthetic tests explicitly supply their
# own destination relationships; live deployment needs independently reviewed policy.
POLICIES = (
    Policy("monarch_aggregation", "Danaus plexippus", "Monarch aggregation developing", "insects",
           eps_meters=200, min_independent_reports=4, minimum_observations=4,
           maximum_cluster_diameter_meters=800, coordinate_uncertainty_limit=200,
           episode_spatial_tolerance=600, qualifying_reports=15, count_requirement=100),
    Policy("black_bear_activity", "Ursus americanus", "Black bear activity", "mammals",
           eps_meters=3000, maximum_cluster_diameter_meters=9000, episode_spatial_tolerance=5000),
    Policy("bald_eagle_fishing", "Haliaeetus leucocephalus", "Bald eagle fishing", "birds",
           trigger="BEHAVIOR_REQUIRED", behaviors=("fishing",), eps_meters=1500,
           maximum_cluster_diameter_meters=4000),
    Policy("humpback_activity", "Megaptera novaeangliae", "Humpback activity", "mammals",
           eps_meters=8000, maximum_cluster_diameter_meters=20000, episode_spatial_tolerance=10000,
           temporal_window_seconds=3*86400),
    Policy("humpback_feeding", "Megaptera novaeangliae", "Humpback feeding", "mammals",
           trigger="BEHAVIOR_REQUIRED", behaviors=("feeding", "lunge_feeding"),
           eps_meters=8000, maximum_cluster_diameter_meters=20000, episode_spatial_tolerance=10000,
           temporal_window_seconds=3*86400),
    Policy("rare_bird", "Haliaeetus pelagicus", "Exceptional bird report", "birds",
           trigger="EXCEPTIONAL_PRESENCE", min_independent_reports=1, minimum_observations=1,
           qualifying_reports=1),
)
