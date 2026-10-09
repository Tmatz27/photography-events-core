# M3A shadow operations

This is developer infrastructure, not a release or production promotion. HA's
local engine and the locked M1 fixture decision pipeline remain authoritative.

Live collection is disabled by default. Explicitly set `CORE_PATTERNS_MODE=shadow`
and `CORE_LIVE_SOURCES=true` together in a development `.env`, with a descriptive
`CORE_SOURCE_USER_AGENT` containing a project/contact URL. No API credential is
needed for these three public reads. Compose passes these settings to Core.
Do not enable this on a production deployment before independent review.

The one-process scheduler polls iNaturalist every 30 minutes and current WFIGS
and NWS every 15 minutes. HTTP runs outside database transactions. Every request
reserves a persistent source quota and a slot at least 1.05 seconds apart.
Provider 429/Retry-After uses the existing persistent scheduler backoff. Product
ceilings are 10,000 requests/day for iNaturalist and a conservative 2,000/day for
each safety/weather source; the latter are not claims about provider limits.
There are no additional services or destructive retention changes.

M3 backoff load/save and quota/lifecycle persistence use the shadow pool; legacy
M1 backoff methods retain their production pool. Default budgets stay 3 seconds
for production DB work, 30 seconds for shadow transactions and 120 seconds per
scheduled source poll. Durable reservations, Retry-After and restart behavior
remain covered. This is one supervised process, not an unattended scheduler.

Only bear/monarch taxa in the source-controlled central-coast rectangle are
searched. Initial iNaturalist reads cover the trailing 14 days. Subsequent
incremental reads use verified `updated_since` with five minutes overlap.
A rotating bulk refresh of up to 200 relevant known numeric IDs detects
corrections that move outside the spatial/taxon/date search. Missing IDs mean
publicly unavailable, not proven deletion. The refresh does not cover all
retained history; old expired records do not establish current evidence.

The known-ID refresh selects only current, unexpired normalized assertions.
An observation retired as publicly unavailable leaves that refresh set. It can
return if a later provider response contains the same UUID through incremental
search (within the taxon/bbox/date filters and `updated_since` cursor/overlap), or
an applicable initial 14-day search. Provider modification, discoverability and
scope must permit that response; rediscovery has no guaranteed schedule. A
bounded retired-ID retry strategy is deferred to operational hardening.

Collection commits raw facts, normalized assertions and diagnostics only. The
accepted M2 lifecycle remains attached to an independently committed M1
assessment. Its next **new** M1 publication captures live facts and recalculates
shadow patterns; reusing an existing assessment ID does not rerun M2. Live polls
do not fabricate a new M1 assessment or overwrite a published M2 run. Corrections
mark prior shadow analysis outdated using consumed source provenance, and
protection increases redact historical output immediately. An operator/test must
continue the existing M1 generation lifecycle to obtain a fresh shadow pattern.
No new production generator or standalone M2 retry was introduced in this slice.

Calibration requires current analysis and current biological source evidence
for `developing_watch`; an outdated pattern is exposed with
`pattern_analysis_state=outdated` and cannot retain that current Watch label.
The accepted M2 source-change grace remains 30 seconds after the changed run
completes; it is not a periodic recomputation. Privacy redaction has no grace.
Live WFIGS destination intersection and source freshness are evaluated directly
from source facts, independently of a new M2 cluster or M1 assessment. A fresh,
complete, successful current-view snapshot is required for `no_intersection`.
A qualifying approved/public/visible active wildfire that intersects Pismo can
supply `hold_candidate` even when a sibling makes the source incomplete. It
requires a current accepted assertion, receipt/poll start within three hours,
native time within the clock tolerance, and the existing native-update-plus-15-day
validity envelope. A duplicate receipt does not renew that native expiry.
Incomplete/stale collection without reliable positive evidence yields `unknown`.
An expired intersecting candidate also yields `unknown`, never a false negative.
Global source freshness remains unknown for an incomplete poll. Identical returning fire
facts reinstate a hold after complete absence, without renewing evidence time.
An older poll cannot override a newer retirement. Explicit CAP cancellations
retain a provider-time replay fence. A future provider update is rejected with
`future_provider_update`, without blocking valid sibling records; protection
still rises on rejected older/future versions. The source-contract skew allowance
is initially one hour, a provisional product policy. Forecast valid periods are
not provider update times and may legitimately be in the future.

Autonomous shadow recomputation, standalone retry/republication and unattended
operation are a separately tracked next task. No automatic M1 rerun or broad
scheduler change is included. Production promotion remains NO.

Authenticated endpoints:

- `/api/v1/debug/source-contracts`: typed contracts, hashes, native timestamps,
  freshness, sanitized parser codes, backoff, reserved request budget, and UTC
  daily traffic/correction/duplicate/privacy counts; latest operational
  `skip_reason_counts`, `outcome_counts` and `poll_outcome` distinguish expected
  version skips, invalid records and ignored entire polls. These additions contain
  counts and fixed codes only; older runs have unavailable (`null`) outcome counts.
- `/api/v1/debug/live/calibration`: Signal/developing Watch, condition and safety
  context. Counts are unknown; behavior and major monarch aggregation remain
  unconfirmed. No production eligibility.
- `/api/v1/debug/patterns`: existing redacted M2 evidence; includes the count of
  rejected identity rows for its published generation.

Raw coordinates, obscured random points, internal centroids, record IDs, provider
descriptions and credentials are not serialized by these debug projections.
Only the existing approved public Pismo destination can be associated with the
monarch policy. A mismatched/restricted existing registry row suppresses that
association. Fire safety uses exact destination intersection, without a buffer
or road-closure inference. `no_intersection` never means travel is safe.

Daily unique records count distinct source external identities read successfully
that UTC day, including repeats; accepted/received are transport record counts.
WFIGS incident pieces can be multiple transport records and one canonical fact.
Correction/duplicate counters count canonical identities. Privacy percentages
are of accepted records, not inferred population prevalence. Requests reserved
may exceed completed-run requests after cancellation/process failure. Day
boundaries are UTC. Native provider age stays separate from successful retrieval;
an empty biological delta without a native timestamp has unknown native age.

G1 `records_rejected`/daily rejected counts refer to invalid inputs. Expected
stale versions/replays use separate structured skip counts and no parser event.
`seen_ids` remains accepted identities for daily unique reporting;
`snapshot_seen_ids` additionally includes parsed, version-skipped identities
without reactivating them. Only a newer complete valid poll retires unseen current
assertions. Explicit CAP references still win over an original alert in either
item order. Entire older polls remain failure/ignored attempts and never certify
a new complete snapshot or advance cursor/watermark.

NWS CAP barrier checks still inspect retained JSONB references per incoming
alert. F4's empty-poll fingerprint benchmark does not measure this lookup.
Benchmark realistic retained-alert volumes, update/cancel chains and replay-heavy
polls before unattended operation; no CAP index/query redesign is included here.

Offline tests run in normal CI. To inspect live contracts manually, inside the
development environment with `PYTHONPATH=src`, run:

```sh
python tools/verify_live_contracts.py --source inaturalist
python tools/verify_live_contracts.py --source wfigs_current
python tools/verify_live_contracts.py --source nws_live_context
# Optional bounded initial-scope measurement (two result pages maximum):
python tools/verify_live_contracts.py --source inaturalist --bounded-poll
```

The commands make very few spaced public requests, mutate no database and emit
only aggregate schema/volume diagnostics. They are not scheduled in CI. Repeated
manual invocations are operator-controlled; production collection uses durable
quotas. `tools/m3_probe.py` is a one-time fixture construction utility; it writes
sanitized fictional IDs/points, not provider coordinates, and should not be used
as a scheduled collector.

Long-term retention and polling should be chosen from measured daily operation.
A single bounded poll is not a daily arrival rate. No normalized 90-day purge,
raw partition, new notification, public map or vision pipeline exists here.

Production monarch qualification remains blocked on a verified dated grove/count
source (candidate Western Monarch Count/Xerces). Research machine access and
terms separately; there is no invented API or scraper in M3A.
