"""Small structured event vocabulary. Never accept arbitrary exception strings."""
import json
import logging
from datetime import UTC, datetime

EVENTS = frozenset({"startup", "schema_issue", "database_unavailable", "database_recovered",
    "source_collection_failure", "source_stale", "parser_failure", "scheduler_failure",
    "api_request_failure", "authentication_failure", "parity_test_failure", "retry_after_clamped",
    "assessment_failure", "assessment_conflict", "report_group_created", "report_group_membership_superseded",
    "cluster_created", "cluster_rejected_incoherent", "cluster_low_precision_excluded", "episode_created",
    "episode_continued", "episode_split", "episode_merged", "episode_ended", "public_location_unavailable",
    "pattern_failure"})
logger = logging.getLogger("photography_events_core")


def event(name, *, source=None, code=None):
    if name not in EVENTS:
        raise ValueError("Unknown structured log event")
    # Only stable machine codes; never DB exception messages, headers or URLs.
    logger.warning(json.dumps({"timestamp": datetime.now(UTC).isoformat(), "event": name,
                               "source": source, "code": code}))
