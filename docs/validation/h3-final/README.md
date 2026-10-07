# H3 accepted code/test-freeze evidence

Unedited artifacts from Core 3ab6a216edc2e7d8d69c2a59001121bf2380cbaa,
[green CI37674959331](https://github.com/Tmatz27/photography-events-core/actions/runs/37674959331),
job112975960561, artifact11507391240. Downloaded ZIP SHA-256 verified:
fc81ccc095e7928ae7937be974d94d6f78237a4e13d61d39e61c01e3b300a579.

273 real PostGIS tests pass; XML comparison retains all accepted261 names and
adds12 H3 cases. h3-performance.json contains full untruncated EXPLAIN ANALYZE
plans and the same-instance pinned unbounded-enrichment/default-budget replay.
No manual ANALYZE or planner settings override was used. Benchmark and pytest
latencies measure completed generation separately from fixture seeding.

acceptance.json records fresh/head, seeded migration chain0001–0006, restarts,
failure injection, actual operator backup/restore, ownership/head/API/episode
preservation and all three restored H3 indexes. collection-performance.json and
m2-performance.json retain N-A and the1000-fresh-report smoke. parity.json records
the18000/0 comparison and pipeline oracle; both frozen fixture recapture cmp
commands passed in the linked job. Review the H3 section of the implementation
packet for design, plan details, statistics variation, limits and status.

The final exact-SHA submission artifact is archived outside this repository with
the external H3_FINAL_RECEIPT.md to avoid a self-referential evidence SHA.
