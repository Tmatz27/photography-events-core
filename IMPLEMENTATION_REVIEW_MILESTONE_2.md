# 1 EXECUTIVE SUMMARY

Milestone 2 implements persistent observation intelligence on accepted M1: qualified report identity, controlled behavior evidence, ordered PostGIS clustering, immutable analytical generations, persistent episode identity/lineage, provenance, privacy-safe debug inspection and held opportunity previews. It remains off by default; only off/shadow modes exist. All 210 Core tests pass against real PostgreSQL/PostGIS; all HA validation jobs pass. A1–A38 are individually exercised.

The normative source is [the reconciled implementation specification](docs/IMPLEMENTATION_SPEC_MILESTONE_2.md). The earlier Gemini assessment supplied architecture context, not implementation authority. Numeric policies and public destinations are provisional architectural fixtures, not ecological claims. No release, tag, version bump, production-default change or independent-review approval is asserted.

# 2 REPOSITORY RECEIPTS

| Repository | Starting main SHA | Validated implementation main SHA |
|---|---|---|
| Tmatz27/photography-events-core | 52db568d6b28cc7716c9329be396786906f65072 | e36c45015243ff39b0e29e7c44df37ca5bca758e |
| Tmatz27/Home-assistant-photography-events | f499d8852ae32e71d8e1b97ed641744fc2b1b084 | c76726ece1e485ece03810087927da344289fba7 |

Both starting checkouts were clean on main and matched origin; checkout/pull --ff-only preceded edits. Work was committed and normally pushed on main. HA changed only CORE_DEVELOPMENT.md. The final documentation commit necessarily cannot contain its own hash; the external submission receipt records the final Core documentation SHA, its exact-SHA CI and both final remote receipts. The implementation SHA above is the code freeze, not a substituted final-documentation SHA.

[Core implementation CI](https://github.com/Tmatz27/photography-events-core/actions/runs/37338718104): SUCCESS at e36c450, 210 passed. [HA CI](https://github.com/Tmatz27/Home-assistant-photography-events/actions/runs/37334287547): all four jobs SUCCESS at c76726e. [Archived evidence](docs/validation/milestone-2/README.md) contains unedited machine results and artifact digest.

Initial runs 37334266424 and 37334766321 failed on the shared PostGIS primitive because an overloaded ST_Transform parameter was inferred as text. Explicit SRID/epsilon/minpoints SQL casts fixed it. Subsequent full runs passed: 37335309875 (201), 37335895254 (206), 37336534824 (208), 37337525562 (210), and 37338718104 (210). Earlier failures are disclosed, not counted as passes.

# 3 ARCHITECTURE ACTUALLY IMPLEMENTED

The existing fixture ingestion transaction stores raw records, normalized assertions, explicit report memberships and canonical behavior rows. Assessment loads current assertions once, applies source-controlled policy admission, selects one representative per qualified report, and runs ordered metric PostGIS density analysis. The publication transaction persists batched cluster headers, memberships, behavior counts, source hashes and dispositions. Episode creation/continuation/ending and material revisions occur only in the winning M1 publication transaction.

Modules: [policy](src/pec/patterns/policy.py), [identity](src/pec/patterns/identity.py), [clustering](src/pec/patterns/clustering.py), [episodes](src/pec/patterns/episodes.py), [engine](src/pec/patterns/engine.py), [API](src/pec/patterns/api.py). Database artifacts and current episode registry are authoritative across process restarts. Debug reads use the current published generation under the existing bounded repeatable-read guard.

# 4 DEVIATIONS FROM THIS PROMPT

Implementation is deliberately limited to tested off/shadow operation. A production pattern promotion/cutover and HA consumption are deferred pending independent review; Core previews cannot become notification-eligible. No biological threshold validation or live observation-source adapter is claimed.

LIVE_CONFIRMATION_REQUIRED and FORECAST_PLUS_CONFIRMATION are named reserved trigger families and reject execution until an explicit future confirmation adapter exists. Only EPSG:3310 and deterministic incoherence rejection are accepted; other projections or recursive cluster splitting require separate validation. Area/unknown-precision evidence is recorded as regional dispositions; no area polygon weighting is implemented. Policy hash changes conservatively end/restart episodes rather than silently interpreting compatibility as equivalence. Sensitive previews are entirely suppressed even if a destination's sensitive_allowed flag exists.

These are explicit limitations of the submitted implementation, not assertions that every future production behavior in the architecture has shipped.

# 5 MIGRATION 0003

[Complete schema inventory](docs/SCHEMA_0003.md) reproduces the exact SQL, including every column, type, foreign key, check, unique constraint and index. The identical executable SQL is also reproduced at the end of this packet. [Migration wrapper](migrations/versions/0003_patterns.py) applies it transactionally after unchanged 0001/0002. Downgrade is forward-only; restore a pre-upgrade backup rather than discard analytical history.

Twelve new tables bring the application inventory to 31 tables, excluding Alembic/PostGIS metadata:

| Table | Responsibility |
|---|---|
| observation_report_groups | Unique qualified namespace/external origin report identity |
| observation_report_group_members | Current and superseded assertion memberships, unique historical membership triple |
| normalized_observation_behaviors | Controlled multiple behaviors per normalized assertion |
| pattern_episodes | Persistent identity, support/state, privacy and split/merge lineage |
| observation_clusters | Generation/policy/member identity, metric geometry, counts and exact provenance |
| cluster_members | Immutable exact assertion/group/membership links; one representative per report |
| cluster_behavior_summaries | Controlled evidence counts by observation/report/provider |
| pattern_generation_runs | Policy/engine hashes and expected artifact cardinalities |
| pattern_generation_sources | Exact run/source/content hash inputs |
| pattern_observation_dispositions | Admission and exclusion reasons per generation/policy/assertion |
| pattern_episode_snapshots | Immutable published episode state tied to its exact cluster |
| pattern_episode_revisions | Append-only references to material snapshots |

Existing normalized assertions gain uncertainty meters, point/area/unknown precision and fixture credibility. Existing assessment opportunities gain a nullable episode FK. Backfill creates provider-qualified report groups and canonical known behavior without inventing missing precision. Fresh install, 0001→0002→0003 legacy-data preservation and repeated head upgrade pass in real DB acceptance. Historical private/internal coordinates and held API identity are preserved.

# 6 REPORT IDENTITY MODEL

Same-provider redelivery retains the existing provider/external-ID upsert semantics. A species assertion is distinct from its underlying documentation report: checklist report_external_id can group multiple assertions. Cross-provider grouping requires an explicit qualified origin namespace and ID accepted by the local fixture adapter. Three providers mirroring one origin yield three provider records/sources but one independent report and one density representative.

Only fixture_observations, fixture_mirror_a and fixture_mirror_b are trusted synthetic namespaces. Unqualified IDs never merge across providers; nearby real observers remain independent. No fuzzy spatial/time/text/species matching establishes identity. Corrections supersede current membership and append a new one; old cluster members reference the exact historical membership triple.

# 7 BEHAVIOR MODEL

Canonical codes are presence, feeding, fishing, courtship, rut, mating, pupping, aggregation, migration, roosting, sow_with_cubs, lunge_feeding and breaching. An assertion can have several codes. Exact explicit aliases include bugling→rut, sow with cubs→sow_with_cubs, lunge feeding→lunge_feeding. Unknown free text is not inferred. Presence alone never implies cubs, fishing or feeding.

Behavior-required policies require repeated independent report evidence. Generic humpback activity and explicit feeding are distinct phenomena; the same explicit assertion can support both. Corrections remove current evidence while immutable historical behavior summaries remain attached to their generation.

# 8 CLUSTER POLICY MODEL

Frozen source-controlled dataclasses define subject, phenomenon key/title, category, trigger/version/compatibility, metric CRS, epsilon, report/observation minimums, temporal/future window, maximum diameter, uncertainty ceiling, continuation gap, spatial tolerance, behavior gates, qualifying report/count thresholds, regional retention, merge permission, operating bounds and approved destination relationships.

Fixture policies cover Monarch aggregation, bear activity, eagle fishing, humpback activity, humpback feeding and exceptional bird presence. Monarch uses eps=200 m, minimum four independent reports/observations, diameter≤800 m, uncertainty≤200 m; its stronger qualification has 15-report and MAX-count criteria. Bear uses eps=3000 m and diameter≤9000 m. Humpback uses eps=8000 m, diameter≤20000 m, a three-day window. Defaults and all exact values are in policy.py; they are product fixtures rather than biological validation.

AGGREGATION_REQUIRED, BEHAVIOR_REQUIRED, COUNT_THRESHOLD and EXCEPTIONAL_PRESENCE execute. Exceptional credible presence bypasses DBSCAN. Integer/finiteness and gate requirements are validated; unsupported live/forecast gates fail explicitly.

# 9 CRS

Storage geometry uses EPSG:4326. Density, centroid, enclosing circle and episode metric comparisons use **EPSG:3310**, the configured California projected meter CRS, within the validated operating envelope (-125,31,-113,43). Calculations are projected approximations, not exact geodesic distances. Admission rejects out-of-envelope points. The current validation whitelist accepts only 3310; a future policy CRS needs new validation.

Prior cluster geometry is transformed through its stored CRS, not a permanently fixed legacy projection assumption. Public destination proximity uses geography ST_DWithin. No untested EPSG:5070 claim is made.

# 10 CLUSTER QUERY

Temporal/subject/precision/credibility/behavior admission precedes projection. Representative selection favors a canonical origin record, then lowest uncertainty, newest observation time and stable provider/external/assertion ties. Typed JSON representative input is expanded in one SQL statement. Explicit parameter casts avoid the ST_Transform overload failure.

ST_SetSRID/ST_MakePoint and ST_Transform construct metric points; ST_ClusterDBSCAN uses ORDER BY stable report hash, epsilon meters and integer minpoints. Ordered aggregation retains logical membership; ST_Collect, ST_Centroid and ST_MinimumBoundingRadius compute artifacts. Centroid and enclosing-circle center are separate geometry columns after conversion to 4326. Noise receives dispositions. EXCEPTIONAL_PRESENCE does not call the density primitive.

# 11 LOW-PRECISION HANDLING

Unknown precision, area records and points above the policy uncertainty ceiling cannot become density representatives or affect centroids/radii. They remain auditable regional dispositions when configured. Regional evidence cannot independently satisfy report/behavior/count qualification or manufacture a public location. No probabilistic uncertainty distribution or area geometry analysis is implemented.

# 12 COHERENCE / CHAIN-LINK PROTECTION

DBSCAN can connect a long chain through short local links. After density membership is established, twice the minimum enclosing radius is compared with maximum_cluster_diameter_meters. An incoherent component is rejected deterministically and its assertions receive incoherent dispositions. There is no recursive fallback that invents local subclusters. Seven linked bear reports in A6 produce zero clusters.

# 13 CLUSTER IMMUTABILITY / GENERATION SCOPE

Cluster identity is generation + policy hash + logical member hash. Membership, behavior summaries, source provenance, policy version/hash, engine hash, geometry and counts are immutable analytical artifacts. A cluster can be assigned to an episode during its winning publication transaction; a partial unique index prevents multiple clusters for one episode/generation.

Superseded evaluation attempts can retain isolated analytical artifacts but cannot mutate episode registry, published snapshots or current generation pointer. Rollback and concurrent older-publication tests exercise this boundary. Expected cluster/snapshot cardinality checks fail safe on incomplete current artifacts.

# 14 CLUSTER PROVENANCE

Each cluster stores assessment ID, policy key/version/hash, engine version/hash, CRS, exact member hash, report memberships, representative choice, evidence windows, observed support times, count metrics, behavior summaries, protection and approved public location. Generation source rows preserve exact content hashes; the retention guard protects these source references.

The engine hash is SHA-256 over normalized source-controlled pattern implementation files. It is persisted per run and cluster and participates in analytical fingerprints. Policy changes and implementation changes make current analytical scope outdated until reevaluation.

# 15 CLUSTER METRICS

| Metric | Meaning |
|---|---|
| provider_record_count | Distinct contributing provider raw records |
| observation_count | Admitted normalized species assertions |
| independent_report_count | Distinct qualified underlying documentation groups |
| independent_source_count | Distinct contributing providers; not proof of independent observers |
| max_single_report_count | Largest explicit individual report count |

Behavior summaries independently count supporting assertions, qualified reports and providers. Multiple mirror rows can increase provider/source counts without increasing independent reports or density points.

# 16 ANIMAL COUNT SEMANTICS

Animal counts are **MAX across explicit individual report counts, never naive SUM**. Counts 10,50,100 produce max_single_report_count=100, not 160. The descriptor is not an exact local population estimate. Validation enforces nonnegative int32 counts. COUNT_THRESHOLD has an explicit requirement; two counts 10 and40 cannot satisfy50 by addition. Null counts do not become zero or inferred population.

# 17 EPISODE MODEL

Persistent pattern_episodes stores phenomenon, subject, policy provenance/compatibility, start/support/end times, active intelligence state, public location, cumulative sensitivity and parent/merge relationships. Published generations have immutable snapshots; revisions reference material snapshots. Developing/qualified are analytical states, distinct from travel readiness and complete M1 assessment.

No Redis, process-local registry or broker is necessary for restart identity. The database registry and published generations survive actual Core restart, PostgreSQL restart and fresh backup restore.

# 18 EPISODE IDENTITY

A new stable key is derived once from initial phenomenon/policy, full generation input watermark and initial logical membership. Continued episodes reuse that persisted key. It is not regenerated from current centroid, current cluster primary key or daily evaluation time. Immutable snapshot identity is distinct from persistent episode identity.

A1–A38 verify restart, equivalent replay and shuffled-input stability. Ended episodes never reopen. Policy-hash changes intentionally produce a new story under new provenance.

# 19 EPISODE CONTINUATION

Candidate episodes require matching phenomenon, subject, policy hash/compatibility, permissible observed-time gap, approved location consistency and metric proximity using enclosing radii/tolerance. Prior report overlap ranks matches. Deterministic strongest-cluster ordering uses independent reports descending, latest support descending and logical cluster hash ascending.

At most one new cluster continues each episode. Observed support time, capped at evaluation now, renews evidence; fetched_at and reevaluation time do not. Future-tolerated reports cannot indefinitely extend support without refetch/validation. Identical evidence in a later generation keeps the key without meaningless revisions.

# 20 EPISODE ENDING

Support expiry or continuation-gap exhaustion ends the episode. A stale rolling-window remnant cannot start a zombie replacement after the allowed gap. Provider withdrawal/removal and expired inputs remove current support. Fresh activity after ending gets a new key. Ending retains immutable history and may create a material revision. A30 verifies refetch at hour120 cannot renew old observations.

# 21 SPLIT/MERGE LINEAGE

A split allows the strongest compatible cluster to continue the parent; remaining compatible clusters start new children with parent_episode_id. A28 verifies 3-report versus2-report deterministic selection.

Default policies disable merge. Approaching clusters alone do not merge identity (A27). Explicit allow_merge requires each old episode to have one compatible candidate and prior report overlap. Survivor ordering is oldest started_at, then created_at, then stable key. Losers end with merged_into_episode_id. Additional real-DB tests exercise explicit permitted merge. HA does not consume this lineage; follow/skip/notification transfer is deferred.

# 22 EPISODE REVISIONS

Every published generation records current episode snapshots consistent with its exact analytical cluster. Material fingerprints include intelligence state, provenance, evidence/counts/behavior, geometry/location, privacy and lineage. Revisions append only when material fingerprint changes. Equivalent new generations preserve identity/metrics and do not append meaningless revisions. Historical summaries remain immutable after provider corrections.

# 23 SENSITIVE LOCATION PROTECTION

Sensitivity is monotonic across retained assertion history and cumulative episode state. Exact geometry remains internal. Authenticated debug DTOs are explicit whitelists; they never include centroids or radius, even for public clusters. Sensitive responses additionally omit metrics, behavior summaries and named public-site metadata; sensitive previews are suppressed.

Immediate protection joins through historical cluster assertion links redact already-published output before reevaluation when a provider changes protection status. Sentinel-coordinate/log and private tiny-site tests check coordinate and metadata leakage. No public confidence is derived solely from obscured regional evidence.

# 24 PUBLIC DESTINATION SELECTION

Only source-controlled policy-approved destinations may be selected, within their configured viewing radius using geography ST_DWithin. Existing destination geometry must agree with the approved coordinates. The analytical centroid/enclosing-circle center is never a travel point.

There is **no arbitrary nearest-location fallback**. Default fixture policies contain no approved destinations. A17 injects one synthetic approved relationship and obtains a held preview at that point; A34 gets no preview without approval. All travel/weather/tide/access/road checks remain unknown in shadow previews, eligible=false, scores zero and no Can't Miss elevation.

# 25 POLICY VERSION/HASH

Canonical sorted-key JSON of the full frozen policy yields SHA-256. Dictionary ordering does not affect it (30 randomized ordering trials). Every numeric, subject, behavior, compatibility, destination and privacy-relevant field participates. There are no executable policy blobs in the DB.

The policy version is a human provenance label, not a substitute for the full hash. Engine source hash is separate. Hash changes preserve old clusters and conservatively end/restart episodes. An explicit compatibility key alone does not silently carry identity over a changed hash.

# 26 PROVIDER CORRECTIONS

Same-provider payload changes supersede old normalized assertions/current memberships, refresh canonical behaviors and source hashes, and affect the next generation. Coordinates, times, counts, behavior, origin identity and protection are recomputed. Historical clusters keep their exact assertion/group/membership links and geometry.

Removing trusted origin mapping yields provider-local identity; A33 changes one report to two without rewriting the old cluster. Withdrawal removes current support. Original raw provider bodies follow accepted M1 upsert semantics and are not version-archived; normalized historical assertions, geometry, behavior, memberships and source content hashes survive. This is a disclosed provenance limit.

# 27 SHADOW MODE

Configuration allows off/shadow only, default off. Off debug is disabled. Shadow calculates current-input analysis and authenticated list/detail inspection without normal opportunity promotion. Missing current analysis is unassessed; source/input, policy/engine, expiry or provisional24-hour collection-age changes mark it outdated.

M1 generation locking, published pointer, bounded read guard, repeatable-read consistency, caches, source-health semantics and error handling are retained. M2 analytical fingerprints are included only for shadow. Debug scope is an analytical statement, not travel approval or a replacement complete M1 assessment.

# 28 PRODUCT SUPPRESSION

Core normalized observations have no direct raw-to-product row path. A1/A23 prove40 scattered Monarchs and500 ordinary Raven records produce no pattern previews and do not flood the normal Core feed. Only a persistent episode can produce one held M2 preview at an approved public point.

Normal Core production API remains accepted M1; it does not promote M2. Existing HA local production engine/card remain unchanged. Therefore this submission demonstrates Core shadow suppression and future adapter behavior, **not a completed HA production cutover**. That distinction is required for safe independent review.

# 29 API CHANGES

Public Opportunity gains nullable pattern_episode_id; existing deterministic calendar opportunities retain NULL (A38). Insects can be represented in held fixture previews; normal M1 category filtering remains mammals/birds. Authenticated debug pattern list/detail routes expose current-generation analytical state, provenance and safe allowed summary fields.

Debug DTOs omit geometry; sensitive DTOs omit evidence/site metadata. Preview Opportunity eligibility/travel gates remain held. No HA card calls debug routes. Existing normal API/error/health contracts and pinned M1 parity remain intact; tests account for three additional debug routes (seven total registered paths).

# 30 HA CHANGES

Only [CORE_DEVELOPMENT.md](../Home-assistant-photography-events/CORE_DEVELOPMENT.md) changed to document M2 off/shadow boundary, nullable relationship and privacy-safe developer inspection. No HA runtime dependency, integration behavior, production card or version changed; HA remains0.16.1. Main-only workflow followed; no PR/release/tag.

CI: portable Python575 run =485 passed+90 skipped; card127 passed/0failed. Actual HA2024.11.3/Python3.12:90 passed. Actual HA2025.3.4/Python3.13:90 passed. HACS validation SUCCESS. Explicit client suite locally13 passed. See the linked exact-SHA HA CI.

# 31 ACCEPTANCE TESTS A1-A38

Each row names a separate real-DB test; input and expected/actual behavior summarize executed assertions, not an unexecuted checklist. A21 additionally has actual Compose process/DB restart evidence in acceptance.json. All38 passed in the210-test implementation run.

| Scenario | Executed test | Input | Expected | Actual asserted result | Result |
|---|---|---|---|---|---|
| A1 | [test_a1_scattered_monarchs](tests/test_patterns_database.py#L78) | 40 scattered Monarch records | No concentration or individual product flood | 0 clusters/episodes; normal Core output ≤1 existing M1 row | PASS |
| A2 | [test_a2_tight_monarch_concentration](tests/test_patterns_database.py#L85) | 12 tight Monarch records | One developing concentration | 1 developing episode; 12 independent reports | PASS |
| A3 | [test_a3_same_record_redelivered](tests/test_patterns_database.py#L91) | Same provider record redelivered | One current provider/assertion/report | 1 raw row, 1 current assertion and membership | PASS |
| A4 | [test_a4_explicit_cross_provider_mirror](tests/test_patterns_database.py#L104) | Three trusted mirrors with qualified common origin | One report, three providers | 1 density representative; counts 1 report / 3 sources / 3 records | PASS |
| A5 | [test_a5_two_real_observers](tests/test_patterns_database.py#L111) | Two nearby real documentation events | Remain independent | 2 report groups and independent reports | PASS |
| A6 | [test_a6_chain_link](tests/test_patterns_database.py#L117) | Seven chain-linked bear points | Reject incoherent candidate | 0 clusters; 7 incoherent dispositions | PASS |
| A7 | [test_a7_bear_activity](tests/test_patterns_database.py#L124) | Four nearby bear reports | One activity pattern | 1 black_bear_activity episode | PASS |
| A8 | [test_a8_bear_without_cubs](tests/test_patterns_database.py#L129) | Bear presence without cub tags | No cub inference | Presence-only summary; no sow_with_cubs evidence | PASS |
| A9 | [test_a9_explicit_sow_cub](tests/test_patterns_database.py#L135) | Three explicit sow/cub + feeding reports | Queryable behavior support | sow_with_cubs summary counts 3 independent reports | PASS |
| A10 | [test_a10_ordinary_bald_eagle](tests/test_patterns_database.py#L142) | One then six ordinary eagle presence records | No fishing pattern | 0 episodes in both generations | PASS |
| A11 | [test_a11_bald_eagle_fishing](tests/test_patterns_database.py#L149) | Three explicit fishing reports | Behavior pattern | 1 bald_eagle_fishing episode with fishing evidence | PASS |
| A12 | [test_a12_humpback_presence](tests/test_patterns_database.py#L155) | Four generic humpback reports | Activity without feeding claim | Only humpback_activity; presence-only behaviors | PASS |
| A13 | [test_a13_humpback_feeding](tests/test_patterns_database.py#L161) | Four explicit lunge-feeding reports | Activity and feeding policies may share observations | 2 phenomena; 8 membership links; lunge-feeding retained | PASS |
| A14 | [test_a14_episode_continuation](tests/test_patterns_database.py#L168) | Compatible next-generation shifted bear cluster | Continue identity | Same episode key | PASS |
| A15 | [test_a15_episode_end_restart](tests/test_patterns_database.py#L175) | 49-hour support gap, then fresh reports at hour 50 | End and create a new story | Old episode ended; fresh episode key differs | PASS |
| A16 | [test_a16_sensitive_cluster](tests/test_patterns_database.py#L185) | Three private records at sentinel coordinates | Internal analysis, public redaction | 3 reports internally; metrics omitted; coordinates absent from API/logs | PASS |
| A17 | [test_a17_centroid_not_destination](tests/test_patterns_database.py#L194) | Cluster with one approved synthetic public viewpoint | Approved destination only; travel checks apply | Preview uses approved coordinates and stays held/ineligible | PASS |
| A18 | [test_a18_expiring_evidence](tests/test_patterns_database.py#L202) | All reports beyond 4-day temporal window | Remove analytical support | 0 current clusters; episode ended | PASS |
| A19 | [test_a19_provider_removes_behavior](tests/test_patterns_database.py#L208) | Provider removes fishing behavior | Current evidence withdrawn, history preserved | 0 new clusters; historical fishing summary unchanged | PASS |
| A20 | [test_a20_rare_bird_bypass](tests/test_patterns_database.py#L217) | Single credible exceptional bird, then noncredible variant | Bypass density only with credibility | Credible singleton episode; noncredible variant hidden | PASS |
| A21 | [test_a21_core_restart](tests/test_patterns_database.py#L224) | New Core database instance and actual container restart | Persistent identity | Same episode key; Compose process/DB restart also verified | PASS |
| A22 | [test_a22_determinism](tests/test_patterns_database.py#L235) | Identical replay, then unchanged inputs in newer generation | Stable outcomes; no meaningless revisions | Same key/metrics; one material revision | PASS |
| A23 | [test_a23_raw_flood](tests/test_patterns_database.py#L246) | 500 ordinary Common Raven records | No raw product flood | 0 patterns/previews; normal Core output ≤1 M1 row | PASS |
| A24 | [test_a24_mirrors_do_not_supply_density](tests/test_patterns_database.py#L253) | Three mirrors under ordinary bear density policy | Mirrors cannot supply three density points | 1 report group; 0 qualifying clusters | PASS |
| A25 | [test_a25_high_uncertainty](tests/test_patterns_database.py#L259) | Four precise Monarch reports plus 15-km-uncertainty record | Exclude imprecise record from centroid | 4 reports, 1 regional disposition; centroid unchanged | PASS |
| A26 | [test_a26_area_observation](tests/test_patterns_database.py#L270) | Four precise points plus area-level report | Area does not act as a precise point | 4 reports; area record retained regionally | PASS |
| A27 | [test_a27_clusters_approach_without_implicit_merge](tests/test_patterns_database.py#L277) | Two existing clusters approach one new cluster | Conservative deterministic identity | One cluster, two active stories; no implicit merge | PASS |
| A28 | [test_a28_episode_split](tests/test_patterns_database.py#L288) | One episode splits into 3-report and 2-report clusters | Strongest continues; child lineage | Parent keeps 3 reports; other cluster gets new child episode | PASS |
| A29 | [test_a29_coordinate_correction](tests/test_patterns_database.py#L298) | Provider moves a point outside local group | Recompute; preserve prior artifact | Current cluster uses 2 reports; historical centroid unchanged | PASS |
| A30 | [test_a30_all_support_expires_without_refetch_renewal](tests/test_patterns_database.py#L307) | Old observations refetched at hour 120 | Fetch does not renew evidence | 0 clusters; episode ended | PASS |
| A31 | [test_a31_regional_corroboration_not_density](tests/test_patterns_database.py#L313) | 12 high-uncertainty Monarch records | Regional retention cannot satisfy density | 12 regional dispositions; 0 clusters/episodes | PASS |
| A32 | [test_a32_count_inflation](tests/test_patterns_database.py#L319) | Counts 10, 50, 100 in three reports | MAX descriptor, no total | max_single_report_count=100; no 160 or exact-population wording | PASS |
| A33 | [test_a33_report_group_correction](tests/test_patterns_database.py#L326) | Trusted mirror origin mapping withdrawn | Correct current grouping; preserve old links | Report count changes 1→2; historical cluster retains one group | PASS |
| A34 | [test_a34_no_approved_destination](tests/test_patterns_database.py#L341) | Strong private cluster without approved destination | No arbitrary nearest fallback | Internal episode; no destination or preview | PASS |
| A35 | [test_a35_input_order_randomization](tests/test_patterns_database.py#L348) | Same five records shuffled over 8 fresh trials | Order-independent membership and identity | Identical cluster hashes, metrics, radii and episode keys | PASS |
| A36 | [test_a36_policy_provenance](tests/test_patterns_database.py#L363) | New policy version/hash | Preserve old provenance; explicit compatibility | Old hash retained; old episode ended and new one started | PASS |
| A37 | [test_a37_sensitive_metadata_redaction](tests/test_patterns_database.py#L374) | Private count/behavior plus tiny named site | Prevent metadata disclosure | Metrics/location/behavior omitted; no sensitive preview | PASS |
| A38 | [test_a38_nonpattern_opportunity](tests/test_patterns_database.py#L383) | Existing Tule Elk deterministic opportunity | Nullable episode relationship | calendar_presence preserved; pattern_episode_id is NULL | PASS |

Additional tests cover raw SQL primitive typing, token authorization, geometry-free list/detail, trusted namespaces, rollback and older concurrent publications, immediate privacy overlays, explicit merge, ambiguous DBSCAN border over six fresh shuffles, checklist grouping, collector/engine/policy freshness, future support, withdrawal and explicit MAX count thresholds. A35 runs eight fresh randomized trials inside one test; trial counts are not inflated into pytest totals.

# 32 M1 REGRESSION RESULTS

Original130 Core M1 tests remain; only schema-version expectation, route count and DB cleanup inventory were adjusted for0003. Original migration SQL, legacy oracle fixtures and accepted behavioral expectations remain unchanged.

Pinned HA oracle4905e35c0668c37737d84685e65d2a806f7c92f7:15 cases×24 fields byte-identical; recapture SHA-256 f246af07a37f5741c4a01904fbb26ef38fa4b929954a58a446b76d9e7db8840d. Nine pipeline fixtures/14 steps byte-identical. Seed20261001,18000 deterministic comparisons, zero mismatches. Concurrency regression R3 performs20 trials inside its test. These are retained regression evidence, not additions to the210 count.

Publication isolation, deadline/recovery, current-generation reads, health, migrations, source semantics, calendar opportunities, cache/privacy and retention gates pass. [Parity machine result](docs/validation/milestone-2/parity.json).

# 33 DATABASE TEST RESULTS

Implementation CI: **210 passed, zero failures/skips**,27.73s. Of these, originalM1=130; addedM2=80 (27 portable,53 DB). Total DB-dependent tests=114 (61M1+53M2). Linux portable run96 passed/114 skipped,1.53s. Windows91 passed/119 skipped:114 DB unavailable locally+five POSIX tests. These local skips are covered by Linux/realDB CI rather than claimed as local execution.

Real environment PostgreSQL18.6/PostGIS3.6.4; acceptance built and ran Core/DB containers. Fresh0003, legacy0001→0002→0003, repeated upgrade, held API, bad token401,1000 synthetic reports→one episode/zero promoted opportunities, Core restart, DB restart, unavailable DB and actual operator backup/restore all pass.

Frozen DB eight warm/eight cold calls with2s guard: max warm2.0123s, max cold2.0048s, zero checked-out connections afterward and recovery=true. Stopped DB live200/ready503/data503. pg_dump custom archive262541bytes (PGDMP), fresh PostGIS DB owner photography_events, pg_restore, migrations/readiness/data and episode/generation history preserved. No actual Unraid/NAS deployment is claimed. [Machine acceptance](docs/validation/milestone-2/acceptance.json), [JUnit](docs/validation/milestone-2/tests.xml), [test log](docs/validation/milestone-2/pytest.log).

# 34 PERFORMANCE / QUERY PLAN

Measured synthetic1000 bear density points plus existing Tule context: one candidate cluster/episode. Python input loading0.034135s, clustering0.024969s. EXPLAIN ANALYZE input execution11.994ms/planning0.469ms; density execution13.258ms/planning0.171ms. [Full untruncated plans and fixture policy](docs/validation/milestone-2/m2-performance.json). These are query measurements, not whole ingestion, production latency or a global-scale SLA.

Input plan uses sorted join results, nested loops/index joins and per-assertion behavior index subplan. Warm cache/in-memory sorting; no temporary I/O. Density plan is typed JSON function scan, deterministic ordered window and sorted aggregation/minimum circle. Whole-window density primitive does not use GiST; spatial/geography indexes support retained geometry inspection/destination operations.

Cluster headers use batched jsonb_to_recordset INSERT RETURNING mapped by logical policy/member key; memberships/behaviors/sources/dispositions use executemany. No per-report network DBSCAN query. Input loader currently materializes all current fixture assertions, then filters policy windows in Python. Ingestion retains per-record M1 isolation; episodes/snapshots still individual writes. This is modest-scale evidence, not unbounded-volume proof. The1000-record smoke uses a30s DB setting; default bounded error tests retain their normal deadlines.

# 35 SECURITY / PRIVACY REVIEW

Token-protected debug endpoints and existing API authentication are tested. DTO construction uses explicit fields; no raw SQL row serialization or geometry passthrough. Invalid input count/precision/behavior/policy values fail validation. DB constraints enforce exact historical relationships and cardinality/representative rules. Queries are parameterized; source-controlled policies contain data rather than executable SQL.

Protected assertions are retained internally but cannot disclose coordinate, radius, private counts, behavior or tiny named-site clues through debug/previews. Immediate privacy rechecks protect historical cluster members. The normal M1 suppression/eligibility contract remains intact. Tests with sentinel coordinates and private metadata pass.

The submission is not an external penetration test. Default LAN HTTP requires operator-managed HTTPS for transport protection. Existing bounded read deadline assumes responsive event-loop scheduling; failure persistence is best effort; readiness is not a full integrity scan. No assertion that repository provenance alone guarantees real-world independent observers is made.

# 36 KNOWN LIMITATIONS

- Only three trusted synthetic fixture namespaces; no live provider onboarding or biologically validated thresholds.
- Exact case-insensitive subject matching; no comprehensive taxonomy or fuzzy identity. Controlled behavior vocabulary is intentionally finite.
- Provisional24-hour source freshness. Metadata sensitivity suppression is conservative; all sensitive previews are suppressed.
- Only validated3310/California bounding envelope; projected distances approximate. No habitat/country geometry filter or second-CRS test.
- Regional dispositions only; no polygon support, probabilistic uncertainty weighting or regional confidence promotion.
- All policy-hash changes restart identity conservatively. Source materiality is conservative at provider-content level.
- Accepted M1 raw-body upsert lacks full raw-payload version archive, though historical normalized evidence/content hashes remain.
- No production M2 promotion or HA cutover; no HA follow/skip/notification-state transfer across split/merge.
- No pattern-history pagination/automatic retention policy, multi-replica certification or sustained production-volume benchmark.
- Input materialization and individual episode writes are modest-scale; per-record ingestion preserved. Query timings exclude total ingestion/end-to-end production work.
- Live/forecast confirmation gates are reserved and reject execution without adapters.
- No actual Unraid/NAS scheduling/deployment; container image digests are not pinned as a reproducibility guarantee.
- Default LAN HTTP needs operator HTTPS; event-loop deadlines, best-effort failure records and readiness scope retain accepted M1 operational limits.
- Existing M1 biological/collector/travel limitations remain; this work does not port all HA production collectors or validate Condor/behavior ecology.

# 37 DEFERRED WORK

No new external source families, map, vision, fuzzy deduplication, ML, Redis, Celery, message broker or distributed task infrastructure were added. No live/forecast confirmation adapter, ecological validation, production promotion, HA consumption/card rewrite, automatic split/merge notification migration, area polygon analytics, additional CRS, full taxonomy, historical raw-body archive or production-scale retention/load certification is implemented. No release/tag/version bump is performed.

# 38 QUESTIONS FOR CLAUDE

1. Try adversarial trusted-origin corrections, checklist species membership and misleading provider/source counts; can any mirror inflate independent reports or rewrite history?
2. Probe count gates with NULL/zero/overflow and repeated animals; can any path add counts or advertise an exact population?
3. Randomize representatives and ambiguous DBSCAN border order; attack long chain components, separate circle center/centroid and uncertainty exclusions.
4. Challenge episode overlap/proximity ties, split selection, explicitly allowed merge survivor ordering, expired remnants and future observation timestamps.
5. Attempt policy/engine/input freshness races and older publication commits; verify registry/snapshot mutation remains inside the winning transaction.
6. Promote sensitivity after publication and inspect every DTO/log/previews/site name/metric; test lack of an approved destination and mismatched destination geometry.
7. Review all0003 constraints/backfill plus actual0001 preservation and restore evidence; examine raw-body historical provenance limit.
8. Verify Core shadow suppression is not mistaken for completed HA production suppression; assess production promotion prerequisites before any cutover.
9. Assess conservative hash-change restart and absent pagination/retention under longer operation; evaluate documented modest-scale query plan.

# 39 NEXT MILESTONE RECOMMENDATION

First perform independent adversarial review and corrections against this exact submission. Then define a separately authorized production-adapter milestone: validate ecology and trusted live source identity, approve public destination policy, supply fresh M1 travel/access/weather checks, define HA episode follow/skip semantics and suppression cutover, and validate retention/volume/operations. Keep M2 off/shadow until those gates are reviewed. This recommendation is not implemented.

## Complete executable migration SQL appendix

The following is an exact copy of migrations/versions/0003_patterns.sql. It inventories all new/altered columns, constraints and indexes; migration0001/0002 remain authoritative for unchanged existing schema.

```sql
CREATE TABLE observation_report_groups (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 origin_namespace TEXT NOT NULL CHECK(length(origin_namespace)>0),
 origin_external_id TEXT NOT NULL CHECK(length(origin_external_id)>0),
 created_at TIMESTAMPTZ NOT NULL,
 UNIQUE(origin_namespace,origin_external_id)
);
CREATE TABLE observation_report_group_members (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 report_group_id BIGINT NOT NULL REFERENCES observation_report_groups(id),
 normalized_observation_id BIGINT NOT NULL REFERENCES normalized_observations(id),
 link_basis TEXT NOT NULL CHECK(link_basis IN ('provider_identity','explicit_origin_id')),
 created_at TIMESTAMPTZ NOT NULL,
 superseded_at TIMESTAMPTZ,
 UNIQUE(id,normalized_observation_id,report_group_id),
 CHECK(superseded_at IS NULL OR superseded_at>=created_at)
);
CREATE UNIQUE INDEX ux_report_current ON observation_report_group_members(normalized_observation_id) WHERE superseded_at IS NULL;
CREATE INDEX ix_report_group_current ON observation_report_group_members(report_group_id) WHERE superseded_at IS NULL;
ALTER TABLE normalized_observations ADD COLUMN coordinate_uncertainty_meters DOUBLE PRECISION CHECK(coordinate_uncertainty_meters>=0 AND coordinate_uncertainty_meters<'Infinity'::float8);
ALTER TABLE normalized_observations ADD COLUMN spatial_precision TEXT NOT NULL DEFAULT 'unknown' CHECK(spatial_precision IN ('point','area','unknown'));
ALTER TABLE normalized_observations ADD COLUMN credible BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE normalized_observation_behaviors (
 normalized_observation_id BIGINT NOT NULL REFERENCES normalized_observations(id),
 behavior_code TEXT NOT NULL CHECK(behavior_code IN ('presence','feeding','fishing','courtship','rut','mating','pupping','aggregation','migration','roosting','sow_with_cubs','lunge_feeding','breaching')),
 created_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(normalized_observation_id,behavior_code)
);
CREATE INDEX ix_behavior_code ON normalized_observation_behaviors(behavior_code,normalized_observation_id);
-- Backfill identity, not precision. Legacy points with unknown accuracy remain unknown for M2.
INSERT INTO observation_report_groups(origin_namespace,origin_external_id,created_at)
 SELECT DISTINCT s.key,COALESCE(r.external_id,'legacy-raw-'||r.id),r.fetched_at
 FROM raw_observations r JOIN sources s ON s.id=r.source_id;
INSERT INTO observation_report_group_members(report_group_id,normalized_observation_id,link_basis,created_at,superseded_at)
 SELECT g.id,n.id,'provider_identity',r.fetched_at,GREATEST(n.superseded_at,r.fetched_at)
 FROM normalized_observations n JOIN raw_observations r ON r.id=n.raw_observation_id
 JOIN sources s ON s.id=r.source_id JOIN observation_report_groups g
 ON g.origin_namespace=s.key AND g.origin_external_id=COALESCE(r.external_id,'legacy-raw-'||r.id);
-- PostgreSQL GREATEST ignores NULL; restore NULL for current assertions explicitly.
UPDATE observation_report_group_members m SET superseded_at=NULL FROM normalized_observations n
 WHERE n.id=m.normalized_observation_id AND n.superseded_at IS NULL;
INSERT INTO normalized_observation_behaviors
 SELECT id,'presence',observed_at FROM normalized_observations WHERE subject_type='species';
INSERT INTO normalized_observation_behaviors
 SELECT id,behavior,observed_at FROM normalized_observations
 WHERE behavior IN ('feeding','fishing','courtship','rut','mating','pupping','aggregation','migration','roosting','sow_with_cubs','lunge_feeding','breaching');
CREATE TABLE pattern_episodes (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 episode_key TEXT NOT NULL UNIQUE,
 phenomenon_key TEXT NOT NULL,
 subject_key TEXT NOT NULL,
 compatibility_key TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('developing','qualified','ended')),
 started_at TIMESTAMPTZ NOT NULL,
 last_supported_at TIMESTAMPTZ NOT NULL,
 ended_at TIMESTAMPTZ,
 public_location_id BIGINT REFERENCES locations(id),
 contains_sensitive_evidence BOOLEAN NOT NULL,
 policy_version TEXT NOT NULL,
 policy_hash TEXT NOT NULL CHECK(length(policy_hash)=64),
 continuation_gap_seconds INTEGER NOT NULL CHECK(continuation_gap_seconds>0),
 parent_episode_id BIGINT REFERENCES pattern_episodes(id),
 merged_into_episode_id BIGINT REFERENCES pattern_episodes(id),
 created_at TIMESTAMPTZ NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL,
 CHECK((status='ended')=(ended_at IS NOT NULL)),
 CHECK(id IS DISTINCT FROM parent_episode_id AND id IS DISTINCT FROM merged_into_episode_id)
);
CREATE INDEX ix_episode_active ON pattern_episodes(phenomenon_key,last_supported_at) WHERE status<>'ended';
CREATE TABLE observation_clusters (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 assessment_run_id BIGINT NOT NULL REFERENCES assessment_runs(id),
 phenomenon_key TEXT NOT NULL,
 cluster_key TEXT NOT NULL CHECK(length(cluster_key)=64),
 pattern_episode_id BIGINT REFERENCES pattern_episodes(id),
 policy_version TEXT NOT NULL,
 policy_hash TEXT NOT NULL CHECK(length(policy_hash)=64),
 engine_version TEXT NOT NULL,
 engine_hash TEXT NOT NULL CHECK(length(engine_hash)=64),
 clustering_crs INTEGER NOT NULL,
 calculated_at TIMESTAMPTZ NOT NULL,
 centroid_internal GEOMETRY(Point,4326) NOT NULL,
 bounding_center_internal GEOMETRY(Point,4326) NOT NULL,
 radius_meters DOUBLE PRECISION NOT NULL CHECK(radius_meters>=0 AND radius_meters<'Infinity'::float8),
 provider_record_count INTEGER NOT NULL CHECK(provider_record_count>0),
 observation_count INTEGER NOT NULL CHECK(observation_count>0),
 independent_report_count INTEGER NOT NULL CHECK(independent_report_count>0),
 independent_source_count INTEGER NOT NULL CHECK(independent_source_count>0),
 max_single_report_count INTEGER CHECK(max_single_report_count>=0),
 window_start TIMESTAMPTZ NOT NULL,
 window_end TIMESTAMPTZ NOT NULL,
 first_observed_at TIMESTAMPTZ NOT NULL,
 last_observed_at TIMESTAMPTZ NOT NULL,
 contains_sensitive_evidence BOOLEAN NOT NULL,
 qualification_state TEXT NOT NULL CHECK(qualification_state IN ('developing','qualified')),
 public_location_id BIGINT REFERENCES locations(id),
 UNIQUE(assessment_run_id,phenomenon_key,cluster_key),
 UNIQUE(id,assessment_run_id,pattern_episode_id),
 CHECK(independent_report_count<=observation_count AND provider_record_count<=observation_count AND independent_source_count<=provider_record_count),
 CHECK(first_observed_at<=last_observed_at AND window_start<window_end)
);
CREATE UNIQUE INDEX ux_cluster_generation_episode ON observation_clusters(assessment_run_id,pattern_episode_id) WHERE pattern_episode_id IS NOT NULL;
CREATE INDEX ix_cluster_episode_history ON observation_clusters(pattern_episode_id,assessment_run_id);
CREATE INDEX ix_cluster_centroid ON observation_clusters USING gist(centroid_internal);
CREATE INDEX ix_location_public_geometry ON locations USING gist(public_geometry);
CREATE TABLE cluster_members (
 cluster_id BIGINT NOT NULL REFERENCES observation_clusters(id),
 normalized_observation_id BIGINT NOT NULL,
 report_group_id BIGINT NOT NULL,
 membership_id BIGINT NOT NULL,
 representative BOOLEAN NOT NULL,
 PRIMARY KEY(cluster_id,normalized_observation_id),
 FOREIGN KEY(membership_id,normalized_observation_id,report_group_id)
 REFERENCES observation_report_group_members(id,normalized_observation_id,report_group_id)
);
CREATE INDEX ix_cluster_member_observation ON cluster_members(normalized_observation_id);
CREATE UNIQUE INDEX ux_cluster_representative ON cluster_members(cluster_id,report_group_id) WHERE representative;
CREATE TABLE cluster_behavior_summaries (
 cluster_id BIGINT NOT NULL REFERENCES observation_clusters(id),
 behavior_code TEXT NOT NULL CHECK(behavior_code IN ('presence','feeding','fishing','courtship','rut','mating','pupping','aggregation','migration','roosting','sow_with_cubs','lunge_feeding','breaching')),
 observation_count INTEGER NOT NULL CHECK(observation_count>0),
 independent_report_count INTEGER NOT NULL CHECK(independent_report_count>0),
 independent_source_count INTEGER NOT NULL CHECK(independent_source_count>0),
 PRIMARY KEY(cluster_id,behavior_code)
);
CREATE TABLE pattern_generation_runs (
 assessment_run_id BIGINT PRIMARY KEY REFERENCES assessment_runs(id),
 policy_hash TEXT NOT NULL CHECK(length(policy_hash)=64),
 engine_hash TEXT NOT NULL CHECK(length(engine_hash)=64),
 mode TEXT NOT NULL CHECK(mode='shadow'),
 calculated_at TIMESTAMPTZ NOT NULL,
 expected_clusters INTEGER NOT NULL CHECK(expected_clusters>=0),
 expected_episodes INTEGER NOT NULL DEFAULT 0 CHECK(expected_episodes>=0)
);
CREATE TABLE pattern_generation_sources (
 assessment_run_id BIGINT NOT NULL REFERENCES pattern_generation_runs(assessment_run_id),
 source_id BIGINT NOT NULL,
 source_run_id BIGINT NOT NULL,
 content_sha256 TEXT,
 PRIMARY KEY(assessment_run_id,source_id),
 FOREIGN KEY(source_run_id,source_id) REFERENCES source_runs(id,source_id)
);
CREATE TABLE pattern_observation_dispositions (
 assessment_run_id BIGINT NOT NULL REFERENCES pattern_generation_runs(assessment_run_id),
 phenomenon_key TEXT NOT NULL,
 normalized_observation_id BIGINT NOT NULL REFERENCES normalized_observations(id),
 disposition TEXT NOT NULL CHECK(disposition IN ('cluster_input','regional','excluded_precision','excluded_time','excluded_credibility','noise','incoherent','behavior_gate')),
 PRIMARY KEY(assessment_run_id,phenomenon_key,normalized_observation_id)
);
CREATE TABLE pattern_episode_snapshots (
 assessment_run_id BIGINT NOT NULL REFERENCES assessment_runs(id),
 pattern_episode_id BIGINT NOT NULL REFERENCES pattern_episodes(id),
 cluster_id BIGINT,
 status TEXT NOT NULL CHECK(status IN ('developing','qualified','ended')),
 started_at TIMESTAMPTZ NOT NULL,
 last_supported_at TIMESTAMPTZ NOT NULL,
 ended_at TIMESTAMPTZ,
 public_location_id BIGINT REFERENCES locations(id),
 contains_sensitive_evidence BOOLEAN NOT NULL,
 policy_version TEXT NOT NULL,
 policy_hash TEXT NOT NULL CHECK(length(policy_hash)=64),
 parent_episode_id BIGINT REFERENCES pattern_episodes(id),
 merged_into_episode_id BIGINT REFERENCES pattern_episodes(id),
 transition_code TEXT NOT NULL CHECK(transition_code IN ('created','continued','split','merged','expired','policy_changed','unsupported','merge_ambiguous')),
 material_fingerprint TEXT NOT NULL CHECK(length(material_fingerprint)=64),
 PRIMARY KEY(assessment_run_id,pattern_episode_id),
 FOREIGN KEY(cluster_id,assessment_run_id,pattern_episode_id)
 REFERENCES observation_clusters(id,assessment_run_id,pattern_episode_id)
);
CREATE TABLE pattern_episode_revisions (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 assessment_run_id BIGINT NOT NULL,
 pattern_episode_id BIGINT NOT NULL,
 recorded_at TIMESTAMPTZ NOT NULL,
 FOREIGN KEY(assessment_run_id,pattern_episode_id)
 REFERENCES pattern_episode_snapshots(assessment_run_id,pattern_episode_id),
 UNIQUE(assessment_run_id,pattern_episode_id)
);
CREATE INDEX ix_episode_revisions ON pattern_episode_revisions(pattern_episode_id,assessment_run_id);
ALTER TABLE assessment_opportunities ADD COLUMN pattern_episode_id BIGINT REFERENCES pattern_episodes(id);
```

