# Operational performance backlog

The independent S1 review observed an M1 slowdown after bulk table loading or
truncation with stale planner statistics. Holding statistics constant produced
approximately 0.13–0.20 s M1 generation with shadow off and on. This is the
reviewer-provided observation, not a new measurement from this correction pass,
and is not currently attributed to M2.

Investigate workload/statistics maintenance in a separately authorized operations
pass. No planner/autovacuum redesign or production ANALYZE behavior was added
here. Benchmarks retain actual fixture loading behavior; timing variation is
reported rather than hidden. No performance SLA is inferred from small warm
synthetic samples.
