"""Per-station collection coverage, separate from evidence age and archive progress."""

from datetime import timedelta

from .models import timestamp


def age(stamp, now, ttl, skew=3600):
    if not stamp:
        return "unknown"
    stamp = timestamp(stamp) if isinstance(stamp, str) else stamp
    if stamp > now + timedelta(seconds=skew):
        return "unknown"
    return "current" if now - stamp <= timedelta(seconds=ttl) else "stale"


def start_station(batch, station, start, end):
    outcome = dict(
        station=station,
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        request_complete=False,
        requests=0,
        successful_requests=0,
        received=0,
        parsed=0,
        rejected=0,
        measurement_asof=None,
        forecast_asof=None,
        measurement_values=0,
        forecast_values=0,
        error_code=None,
    )
    batch.environment["stations"].append(outcome)
    return outcome


def finish_station(outcome, batch, records, rejected, received, requests, error=None, *, successes=0):
    outcome.update(
        requests=requests,
        successful_requests=successes,
        received=batch.received - received,
        parsed=len(batch.records) - records,
        rejected=len(batch.rejected) - rejected,
        request_complete=error is None,
        error_code=error,
    )
    for fact in batch.records[records:]:
        note_fact(outcome, fact, count=True)
    outcome["outcome"] = (
        "failed"
        if error
        else "incomplete"
        if outcome["rejected"]
        else "data"
        if outcome["measurement_asof"] or outcome["forecast_asof"]
        else "no_observations"
    )


def note_fact(outcome, fact, *, count=False):
    if fact.withdrawn or fact.numeric_value is None:
        return
    kind = fact.evidence_kind
    if kind not in ("measurement", "forecast"):
        return
    if count:
        outcome[kind + "_values"] += 1
    stamp = fact.valid_at if kind == "measurement" else fact.issued_at
    previous = outcome[kind + "_asof"]
    if stamp and (previous is None or stamp > timestamp(previous)):
        outcome[kind + "_asof"] = stamp.isoformat()


def coverage(context, now, contract):
    if not context:
        return None
    history = context["mode"] == "historical"
    stations = []
    for original in context.get("stations", []):
        row = dict(original)
        for kind in ("measurement", "forecast"):
            row[kind + "_freshness"] = (
                "not_applicable"
                if history
                else "unknown"
                if not row["request_complete"]
                or row["rejected"]
                or row["outcome"] in ("failed", "incomplete")
                else age(
                    row[kind + "_asof"], now, contract.freshness_seconds, contract.provider_clock_skew_seconds
                )
            )
        row["state"] = (
            row["outcome"]
            if history or row["outcome"] in ("failed", "incomplete")
            else row["measurement_freshness"]
            if row["measurement_asof"]
            else "no_observations"
        )
        stations.append(row)
    states = {
        name: sum(r["state"] == name for r in stations)
        for name in ("current", "stale", "no_observations", "failed", "incomplete", "data", "unknown")
    }
    return dict(
        mode=context["mode"],
        configured_stations=len(stations),
        successful_stations=sum(r["request_complete"] for r in stations),
        successful_requests=sum(r["successful_requests"] for r in stations),
        states=states,
        stations=stations,
        measurement_freshness=aggregate(stations, "measurement") if not history else "not_applicable",
        forecast_freshness=aggregate(stations, "forecast") if not history else "not_applicable",
    )


def aggregate(stations, kind):
    values = [r[kind + "_freshness"] for r in stations]
    if values and all(v == "current" for v in values):
        return "current"
    return "stale" if "stale" in values else "unknown"


def required_asof(context):
    """A newest station or forecast must never conceal missing required evidence."""
    required = (
        ("measurement", "forecast")
        if context["dataset"] == "nwps" and context["mode"] == "current"
        else ("measurement",)
    )
    stamps = []
    for row in context["stations"]:
        if not row["request_complete"] or row["rejected"]:
            return None
        for kind in required:
            if not row[kind + "_asof"]:
                return None
            stamps.append(timestamp(row[kind + "_asof"]))
    return min(stamps) if stamps else None


def history_health(row, now, interval):
    if not row or not row.get("enabled") or not row.get("status"):
        return "unknown"
    if row["status"] != "success" or row.get("incomplete"):
        return "unknown"
    # Process health: archived evidence is SUPPOSED to be older than today.
    return age(row.get("completed_at") or row.get("last_success_at"), now, max(2 * interval, 3600))
