# Milestone 1 validation evidence

These files snapshot successful GitHub Actions results for the implementation
SHAs recorded in the master review packet. The final documentation-only commit
has a separate CI run recorded in the delivered submission receipt.

- `core-ci.json`: Core run, job, artifact identity and test counts.
- `core-acceptance.json`: actual Docker/PostGIS, restart and operator-script backup/restore outcomes.
- `core-pytest.log`, `core-tests.xml`: all 71 container tests, with no failures/skips.
- `ha-ci.json`: final HA main run and exact portable/card/real-HA test counts.

No database files, backup archives, production observations or credentials are
included. The archive digest in `core-ci.json` identifies the downloaded CI ZIP.
The 56,846-byte backup size belongs to that run; later runs can differ.

## Reproduction

Use a disposable Linux checkout with Docker Engine / Compose v2 and Python 3.12.
Install `requirements-dev.lock`, set `PYTHONPATH=src`, and run:

```sh
python -m ruff check src migrations tools tests
python -m compileall -q src migrations tools
python -m pytest -q
python tools/acceptance.py
```

The last command generates ephemeral secrets in-process, overrides all DB/Core
storage paths into `evidence/`, uses the private Compose network, tests a
separate `photography_events_test` database, and restores to
`photography_events_restore_test`. It requires free loopback ports 8099 and 8100.
Do not run it in a production checkout. Its teardown removes only the disposable
Compose containers/networks and its named temporary restore container.

To independently regenerate the legacy oracle, create a separate HA clone,
checkout `4905e35c0668c37737d84685e65d2a806f7c92f7`, install its existing
`beautifulsoup4` dependency, and run:

```sh
python tools/capture_legacy_parity.py --legacy-repo /path/to/pinned-ha-clone
python -m pytest -q tests/test_parity.py
```

The capture tool rejects a different HA HEAD and executes the real legacy
engine. Review any fixture diff; do not accept changed expectations merely to
make parity pass. Current final HA main includes the client scaffold, so a
separate pinned clone is necessary for oracle regeneration.

HA reproduction uses the commands and compatibility matrix in `ha-ci.json`.
For portable Python tests install the test dependencies from HA's validation
workflow; the full HA Store/coordinator tests require the recorded real HA
versions. The existing local engine remains authoritative.
