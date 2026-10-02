"""Explicit public contract. No raw evidence or private coordinates in DTOs."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Presentation = Literal["cant_miss", "watching", "planner", "held", "bird_spectacle", "bird_encounter"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Version(Contract):
    core_version: str
    api_version: str
    schema_version: str


class Health(Version):
    status: Literal["alive", "ready"]


class PublicLocation(Contract):
    key: str
    name: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    policy: Literal["curated_public_site", "withheld"] = "curated_public_site"


class Gear(Contract):
    take: str = ""
    optional: list[str] = Field(default_factory=list)
    skip: list[str] = Field(default_factory=list)
    start: str = ""
    support: str = ""
    technique: str = ""
    video: str = ""
    drone: str = ""
    drone_status: str = ""


class Opportunity(Contract):
    assessment_id: int | None = None
    occurrence_key: str
    phenomenon_key: str
    title: str
    category: Literal["mammals", "birds"]
    location: PublicLocation
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    presentation: Presentation
    eligibility: bool
    significance: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    urgency: int = Field(ge=0, le=100)
    evidence_state: str
    access_state: str
    safety_state: Literal["safe", "caution", "unsafe", "unknown"]
    condition_state: Literal["not_required", "unknown"] = "not_required"
    drive_minutes: float | None = Field(default=None, ge=0)
    drive_basis: str
    reason: str
    awaiting: str
    blockers: list[str]
    held: bool
    watching: bool
    bird_classification: Literal["spectacle", "encounter"] | None = None
    gear: Gear
    ethics: str
    safety_summary: str
    safety_notes: list[str]
    best_time_of_day: str = ""
    detail: str = ""
    data_as_of: AwareDatetime
    valid_until: AwareDatetime
    definition_key: str
    definition_version: str
    definition_hash: str
    engine_version: str


class OpportunityList(Version):
    assessment_id: int | None = None
    generated_at: AwareDatetime
    data_as_of: AwareDatetime | None
    assessment_state: Literal["complete", "incomplete", "degraded"]
    missing_required_sources: list[str]
    degraded_sources: list[str]
    items: list[Opportunity]


class SourceHealth(Contract):
    key: str
    state: Literal["UP", "STALE", "DOWN"]
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    provider_updated_at: AwareDatetime | None
    error_code: str | None


class SourceHealthList(Version):
    generated_at: AwareDatetime
    items: list[SourceHealth]


class ErrorDetail(Contract):
    code: str
    message: str


class Error(Contract):
    error: ErrorDetail

