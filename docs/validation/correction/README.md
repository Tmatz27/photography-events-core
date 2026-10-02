# Independent review correction evidence

These files are copied from the successful Core implementation run
[36966654374](https://github.com/Tmatz27/photography-events-core/actions/runs/36966654374)
at b816e378975e88a5183368d6089ac092c34ae068. The artifact ZIP checksum was verified
against GitHub's sha256 digest before extraction. See ci.json for run/job IDs,
exact Core and HA SHAs, counts and the archive digest.

- [acceptance.json](acceptance.json): real image/Compose/PostGIS, migration,
  restart, frozen DB and actual operator backup/restore results.
- [pytest.log](pytest.log) and [tests.xml](tests.xml): all 130 Core tests pass,
  including 61 DB-dependent cases.
- [parity.json](parity.json): pinned legacy oracle, nine pipeline cases and
  18,000 evaluator comparisons with zero mismatches.
- [frozen-database.json](frozen-database.json): eight warm and eight cold paused
  DB requests, bounded failures, zero checked-out connections and recovery.
- [ci.json](ci.json): Core/HA metadata and confirmed HA matrix results.

HA's [run 36966194592](https://github.com/Tmatz27/Home-assistant-photography-events/actions/runs/36966194592)
is successful at f499d8852ae32e71d8e1b97ed641744fc2b1b084. Job logs independently
confirm 575 portable tests (90 intentional real-HA skips), 127 card tests, and
90 real-HA tests in each compatibility environment.

These are implementation-SHA snapshots. The final documentation-SHA run is
verified and linked in the external correction receipt; it does not require
editing these historical evidence files after every documentation commit.
No secrets, database contents, backup archives or raw private records are stored here.

