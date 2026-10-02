"""Small structured event vocabulary. Never accept arbitrary exception strings."""
import json
import logging
from datetime import UTC, datetime

EVENTS = frozenset({"startup", "schema_issue", "database_unavailable", "database_recovered",
    "source_collection_failure", "source_stale", "parser_failure", "scheduler_failure",
    "api_request_failure", "authentication_failure", "parity_test_failure", "retry_after_clamped",
    "assessment_failure", "assessment_conflict"})
logger = logging.getLogger("photography_events_core")


def event(name, *, source=None, code=None):
    if name not in EVENTS:
        raise ValueError("Unknown structured log event")
    # Only stable machine codes; never DB exception messages, headers or URLs.
    logger.warning(json.dumps({"timestamp": datetime.now(UTC).isoformat(), "event": name,
                               "source": source, "code": code}))
