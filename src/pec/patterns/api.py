"""Redacted, authenticated shadow inspection. Never a raw observation feed."""
from datetime import timedelta
from typing import Literal
from pydantic import Field

from sqlalchemy import text

from ..database import AssessmentConflict, InvalidStoredProduct, VERSION
from ..schemas import Contract, Gear, Opportunity, PublicLocation


class Metrics(Contract):
    provider_record_count: int
    observation_count: int
    independent_report_count: int
    independent_source_count: int
    max_single_report_count: int | None
    behaviors: list[str]


class PatternView(Contract):
    episode_key: str
    phenomenon_key: str
    state: Literal["developing", "qualified", "ended"]
    policy_version: str
    policy_hash: str
    transition: str
    redacted: bool
    summary: str
    metrics: Metrics | None = None
    location: PublicLocation | None = None


class ClusterView(Contract):
    cluster_id: int
    phenomenon_key: str
    policy_version: str
    policy_hash: str
    redacted: bool
    metrics: Metrics | None = None


class CoherenceMetrics(Contract):
    candidate_observation_count: int
    independent_report_count: int
    candidate_radius_meters: float
    candidate_diameter_meters: float
    recovered_cluster_count: int


class CoherenceView(Contract):
    phenomenon_key: str
    state: Literal["coherence_rejected"] = "coherence_rejected"
    policy_version: str
    policy_hash: str
    primary_eps_meters: float
    maximum_diameter_meters: float
    fallback_eps_meters: float | None
    fallback_attempted: bool
    fallback_result: str
    redacted: bool
    metrics: CoherenceMetrics | None = None


class PatternResponse(Contract):
    core_version: str
    api_version: str
    schema_version: str
    assessment_id: int | None
    mode: Literal["off", "shadow"]
    analysis_state: Literal["disabled", "unassessed", "current", "outdated"]
    items: list[PatternView]
    clusters: list[ClusterView]
    preview_opportunities: list[Opportunity]
    coherence_rejections: list[CoherenceView] = Field(default_factory=list)
    identity_rejected_count: int = 0


def metrics(row):
    return Metrics(**{key:row[key] for key in ("provider_record_count","observation_count",
        "independent_report_count","independent_source_count","max_single_report_count")},behaviors=row["behaviors"])


def summary(value):
    result = (f"{value.observation_count} observations from {value.independent_report_count} independent reports "
              f"across {value.independent_source_count} contributing providers.")
    if value.max_single_report_count is not None:
        result += f" Largest single report: {value.max_single_report_count}; not an estimated animal total."
    return result


def preview(row, view, assessment, now):
    # Provisional fixture policies are never actionable. All existing travel
    # gates remain unfulfilled, rather than assuming a curated point is safe/open.
    if view.redacted or view.location is None or row["cluster_id"] is None or view.state == "ended":
        return None
    return Opportunity(assessment_id=assessment["id"],pattern_episode_id=row["pattern_episode_id"],
        occurrence_key="pattern-"+view.episode_key,phenomenon_key=view.phenomenon_key,
        title="Pattern review: "+view.phenomenon_key.replace("_"," "),category=row["category"],
        location=view.location,starts_at=row["started_at"],ends_at=max(now,row["last_supported_at"])+timedelta(hours=1),
        presentation="held",eligibility=False,significance=0,confidence=0,urgency=0,
        evidence_state="pattern_"+view.state,access_state="unknown",safety_state="unknown",condition_state="unknown",
        drive_basis="not_assessed",reason=view.summary,awaiting="Independent policy review and current travel checks.",
        blockers=["shadow policy","access not assessed","safety not assessed","conditions not assessed","drive not assessed"],
        held=True,watching=False,gear=Gear(),ethics="Use approved public destinations; keep wildlife distance.",
        safety_summary="Travel safety has not been assessed.",safety_notes=[],data_as_of=assessment["data_as_of"],
        valid_until=assessment["valid_until"],definition_key=view.phenomenon_key,definition_version=view.policy_version,
        definition_hash=view.policy_hash,engine_version=VERSION["core_version"])


async def read(db, now, episode_key=None):
    async def operation(c):
        await db._check(c)
        assessment = (await c.execute(text("""SELECT a.* FROM assessment_current p
            JOIN assessment_runs a ON a.id=p.assessment_run_id WHERE p.id=1"""))).mappings().first()
        aid = assessment["id"] if assessment else None
        empty = dict(**VERSION,assessment_id=aid,mode=db.patterns_mode,items=[],clusters=[],preview_opportunities=[])
        if db.patterns_mode == "off":
            return PatternResponse(**empty,analysis_state="disabled")
        if assessment is None:
            return PatternResponse(**empty,analysis_state="unassessed")
        if assessment["status"] != "published":
            raise InvalidStoredProduct()
        conflict = (await c.execute(text("""SELECT EXISTS(SELECT 1 FROM assessment_runs
            WHERE data_as_of=:stamp AND error_code='input_conflict')"""),{"stamp":assessment["data_as_of"]})).scalar_one()
        if conflict:
            raise AssessmentConflict()
        run = (await c.execute(text("SELECT * FROM pattern_generation_runs WHERE assessment_run_id=:aid"),
                               {"aid":aid})).mappings().first()
        if run is None or run["status"] != "published":
            return PatternResponse(**empty,analysis_state="unassessed")
        rows = [dict(r) for r in (await c.execute(text("""SELECT c.*,
            (c.contains_sensitive_evidence OR COALESCE(protection.sensitive,FALSE)) AS protected,
            ARRAY(SELECT behavior_code FROM cluster_behavior_summaries b WHERE b.cluster_id=c.id ORDER BY behavior_code) AS behaviors
            FROM observation_clusters c LEFT JOIN LATERAL (
            SELECT bool_or(n.sensitive) AS sensitive FROM cluster_members m
            JOIN normalized_observations n ON n.id=m.normalized_observation_id WHERE m.cluster_id=c.id
            ) protection ON TRUE WHERE c.assessment_run_id=:aid ORDER BY c.phenomenon_key,c.cluster_key"""),
            {"aid":aid})).mappings()]
        if len(rows) != run["expected_clusters"]:
            raise InvalidStoredProduct()
        clusters = {row["id"]:row for row in rows}
        snapshots = [dict(r) for r in (await c.execute(text("""SELECT s.*,e.episode_key,e.phenomenon_key,
            l.key AS location_key,l.name AS location_name,ST_X(l.public_geometry) AS longitude,
            ST_Y(l.public_geometry) AS latitude,l.sensitivity AS location_sensitivity
            FROM pattern_episode_snapshots s JOIN pattern_episodes e ON e.id=s.pattern_episode_id
            LEFT JOIN locations l ON l.id=s.public_location_id WHERE s.assessment_run_id=:aid
            ORDER BY e.episode_key"""),{"aid":aid})).mappings()]
        if len(snapshots) != run["expected_episodes"]:
            raise InvalidStoredProduct()
        changed = (await c.execute(text("""SELECT EXISTS(
            SELECT 1 FROM pattern_generation_sources p JOIN sources s ON s.id=p.source_id
            JOIN LATERAL(SELECT * FROM source_runs WHERE source_id=p.source_id ORDER BY completed_at DESC,id DESC LIMIT 1) r ON TRUE
            WHERE p.assessment_run_id=:aid AND (NOT s.enabled OR r.status<>'success'
            OR r.completed_at<:stale
            OR (r.content_sha256 IS DISTINCT FROM p.content_sha256 AND r.completed_at<=:grace)))"""),
            {"aid":aid,"grace":now-db.grace,"stale":now-timedelta(hours=24)})).scalar_one()
        state = "outdated" if changed or assessment["valid_until"]<=now else "current"
        from .engine import engine_hash, policy_hash
        if run["policy_hash"] != policy_hash(db.pattern_policies) or run["engine_hash"] != engine_hash():
            state = "outdated"
        source_count = (await c.execute(text("SELECT count(*) FROM pattern_generation_sources WHERE assessment_run_id=:aid"),
                                       {"aid":aid})).scalar_one()
        if source_count == 0:
            state = "unassessed"
        diagnostics=[]
        rejected=(await c.execute(text("""SELECT d.*,(d.contains_sensitive_evidence OR EXISTS(
            SELECT 1 FROM pattern_observation_dispositions p JOIN normalized_observations n
            ON n.id=p.normalized_observation_id WHERE p.assessment_run_id=d.assessment_run_id
            AND p.phenomenon_key=d.phenomenon_key AND n.sensitive) OR EXISTS(
            SELECT 1 FROM pattern_episode_snapshots snap JOIN pattern_episodes ep ON ep.id=snap.pattern_episode_id
            WHERE snap.assessment_run_id=d.assessment_run_id AND ep.phenomenon_key=d.phenomenon_key
            AND snap.contains_sensitive_evidence)) AS protected
            FROM pattern_coherence_rejections d WHERE d.assessment_run_id=:aid
            ORDER BY d.phenomenon_key,d.candidate_key"""),{"aid":aid})).mappings()
        for row in rejected:
            value=None if row["protected"] else CoherenceMetrics(**{key:row[key] for key in CoherenceMetrics.model_fields})
            diagnostics.append(CoherenceView(**{key:row[key] for key in (
                "phenomenon_key","policy_version","policy_hash","primary_eps_meters","maximum_diameter_meters",
                "fallback_eps_meters","fallback_attempted","fallback_result")},redacted=row["protected"],metrics=value))
        views, previews = [], []
        policies = {p.key:p for p in db.pattern_policies}
        for row in snapshots:
            if episode_key and row["episode_key"] != episode_key:
                continue
            cluster = clusters.get(row["cluster_id"])
            redacted = row["contains_sensitive_evidence"] or bool(cluster and cluster["protected"])
            value = metrics(cluster) if cluster and not redacted else None
            location = None
            if not redacted and row["location_sensitivity"] == "public" and row["latitude"] is not None:
                location = PublicLocation(key=row["location_key"],name=row["location_name"],
                                          latitude=row["latitude"],longitude=row["longitude"])
            view = PatternView(episode_key=row["episode_key"],phenomenon_key=row["phenomenon_key"],state=row["status"],
                policy_version=row["policy_version"],policy_hash=row["policy_hash"],transition=row["transition_code"],
                redacted=redacted,metrics=value,location=location,
                summary="Protected evidence; details withheld." if redacted else summary(value) if value else "No current qualifying cluster.")
            views.append(view)
            policy = policies.get(row["phenomenon_key"])
            if policy and policy.hash == row["policy_hash"]:
                row["category"] = policy.category
                product = preview(row,view,assessment,now)
                if product:
                    previews.append(product)
        public_clusters = [ClusterView(cluster_id=row["id"],phenomenon_key=row["phenomenon_key"],
            policy_version=row["policy_version"],policy_hash=row["policy_hash"],redacted=row["protected"],
            metrics=None if row["protected"] else metrics(row)) for row in rows] if episode_key is None else []
        return PatternResponse(**VERSION,assessment_id=aid,mode="shadow",analysis_state=state,
                               items=views,clusters=public_clusters,preview_opportunities=previews,
                               coherence_rejections=diagnostics,identity_rejected_count=run['identity_rejected_count'])
    return await db.transaction(operation)
