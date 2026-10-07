# H3 query-plan evidence before migration 0006

Unedited h3-performance.json from Core d064497ff778aade58d43b0cbd5c6d7182c275e2,
[run 37671509592](https://github.com/Tmatz27/photography-events-core/actions/runs/37671509592),
artifact 11505721267. Downloaded ZIP SHA-256 verified:
34ef864e8cfce4500c59bef7a868b871dbe1a4d5efef9cdd8a9f3565de0c4518.

This is diagnostic evidence from a FAILED workflow, not final acceptance. Its
271 real PostGIS tests passed, but the subsequent existing 1000-fresh-report
smoke failed the shadow enrichment deadline. The saved history benchmark itself
published with 4-row working sets at 0/2000/5000/10000/25000 retained old rows.

The plans demonstrate why indexes/join constraints were required despite those
publication results: dependency lookup visited normalized/raw historical rows
per key; retirement visited all existing current membership assertions. At
25000 retained old rows, dependency EXPLAIN execution was 191.337 ms. The old
c1db87e unbounded enrichment replay failed the unchanged default budget at 25000;
10000 completed on this faster runner. Neither failure nor hardware variation
is hidden. No manual ANALYZE or planner-setting override was used.

Final bounded plans and full green acceptance are recorded separately in the
H3 review section and h3-final evidence folder.
