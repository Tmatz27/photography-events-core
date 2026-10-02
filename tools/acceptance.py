"""Real Docker/PostGIS restart and custom-format restore acceptance.

Run only in a disposable checkout. Artifacts contain no secrets. This script
does not touch an Unraid host or production NAS.
"""
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
COMPOSE = ["docker", "compose", "-f", "compose.yaml", "-f", "compose.ci.yaml"]
results = {}


def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def compose(*args, **kwargs):
    return run(*COMPOSE, *args, **kwargs)


def check(path, status=200, token=True, port=8099):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
        headers={"Authorization": "Bearer " + os.environ["CORE_API_TOKEN"]} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=6) as r:
            code, payload = r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        code, payload = exc.code, json.load(exc)
    assert code == status, (path, code, status)
    return payload


def wait_ready(port=8099):
    for _ in range(40):
        try:
            return check("/health/ready", port=port)
        except (AssertionError, OSError):
            time.sleep(2)
    raise AssertionError("Core readiness timed out")


def main():
    EVIDENCE.mkdir(exist_ok=True)
    for key in ("POSTGRES_ADMIN_PASSWORD", "POSTGRES_PASSWORD", "CORE_API_TOKEN"):
        os.environ[key] = secrets.token_hex(32)
    os.environ.update(DB_DATA_PATH=str(EVIDENCE / "db"), CORE_DATA_PATH=str(EVIDENCE / "core"), CORE_BIND_IP="127.0.0.1")
    compose("config", "-q")
    compose("build")
    results["container_build"] = "passed"
    try:
        compose("up", "-d", "--wait", "--wait-timeout", "150")
        results["startup"] = wait_ready()
        versions = compose("exec", "-T", "photography-events-db", "psql", "-U", "postgres", "-d", "photography_events", "-Atc", "SELECT version(),postgis_full_version()", capture_output=True, text=True).stdout
        results["database_versions"] = versions.strip()
        compose("exec", "-T", "photography-events-db", "createdb", "-U", "postgres", "-O", "photography_events", "photography_events_test")
        compose("exec", "-T", "photography-events-db", "psql", "-U", "postgres", "-d", "photography_events_test", "-c", "CREATE EXTENSION postgis")
        test_exec = ("exec", "-T", "-e", "POSTGRES_DB=photography_events_test", "photography-events-core", "python")
        compose(*test_exec, "-m", "alembic", "upgrade", "0001")
        compose(*test_exec, "-m", "alembic", "downgrade", "base")
        compose(*test_exec, "-m", "alembic", "upgrade", "0001")
        results["migration_0001_round_trip"] = "passed"
        compose(*test_exec, "tools/migration_acceptance.py", "seed")
        compose(*test_exec, "-m", "alembic", "upgrade", "head")
        compose(*test_exec, "tools/migration_acceptance.py", "verify")
        results["R20_migration_0001_to_0002"] = "identity and provider data preserved; API reads held legacy context"
        compose(*test_exec, "-m", "alembic", "upgrade", "head")
        results["repeat_migration"] = "passed"
        with (EVIDENCE / "pytest.log").open("w") as log:
            try:
                compose(*test_exec, "tools/database_tests.py", stdout=log, stderr=subprocess.STDOUT)
            finally:
                compose("cp", "photography-events-core:/tmp/core-tests.xml", str(EVIDENCE / "tests.xml"))
        results["migration_0002_downgrade"] = "forward-only; restore pre-upgrade backup instead of losing history"
        compose("exec", "-T", "photography-events-core", "python", "-m", "pec", "tests/fixtures/legacy_tule_elk.json")
        key = "tule_elk_rut-2026-09-15"
        first = check("/api/v1/opportunities/" + key)
        results["fixture_readable"] = first["occurrence_key"]
        check("/api/v1/opportunities", 401, token=False)
        results["bad_token"] = "401"
        compose("restart", "photography-events-core")
        wait_ready()
        assert check("/api/v1/opportunities/" + key)["occurrence_key"] == key
        results["core_restart"] = "data preserved"
        probe = subprocess.Popen([*COMPOSE, "exec", "-T", "photography-events-core", "python", "tools/frozen_database_probe.py"], cwd=ROOT)
        def wait_marker(name):
            for _ in range(100):
                if probe.poll() is not None:
                    raise AssertionError("Frozen database probe exited before handshake")
                marker = subprocess.run([*COMPOSE, "exec", "-T", "photography-events-core", "test", "-f", "/tmp/" + name],
                                        cwd=ROOT, capture_output=True)
                if marker.returncode == 0:
                    return
                time.sleep(0.1)
            raise AssertionError("Frozen database probe handshake timed out")
        wait_marker("frozen-ready")
        compose("pause", "photography-events-db")
        try:
            compose("exec", "-T", "photography-events-core", "touch", "/tmp/frozen-go")
            wait_marker("frozen-done")
        finally:
            compose("unpause", "photography-events-db")
            compose("exec", "-T", "photography-events-core", "touch", "/tmp/frozen-recover")
        assert probe.wait(timeout=30) == 0
        compose("cp", "photography-events-core:/tmp/frozen-results.json", str(EVIDENCE / "frozen-database.json"))
        results["R19_frozen_database"] = json.loads((EVIDENCE / "frozen-database.json").read_text())
        compose("stop", "photography-events-db")
        check("/health/live")
        check("/health/ready", 503)
        check("/api/v1/opportunities", 503)
        results["database_stopped"] = "live 200, ready 503, data 503"
        compose("start", "photography-events-db")
        wait_ready()
        assert check("/api/v1/opportunities/" + key)["occurrence_key"] == key
        results["database_restart"] = "ready and data preserved"
        # Execute the operator scripts themselves, not merely equivalent commands.
        backup_result = run("sh", "scripts/backup.sh", env={**os.environ, "BACKUP_DIR": str(EVIDENCE / "backups")},
                            capture_output=True, text=True)
        backup = Path(backup_result.stdout.strip())
        assert backup.read_bytes()[:5] == b"PGDMP"
        results["backup_bytes"] = backup.stat().st_size
        run("sh", "scripts/restore.sh", str(backup), "photography_events_restore_test")
        results["operator_scripts"] = "backup.sh and restore.sh executed successfully"
        owners = compose("exec", "-T", "photography-events-db", "psql", "-U", "postgres", "-d", "photography_events_restore_test", "-Atc",
            "SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='opportunities'", capture_output=True, text=True).stdout.strip()
        assert owners == "photography_events", owners
        results["restored_application_owner"] = owners
        # Same Core service image and app user, fresh container pointed at restored DB.
        compose("run", "-d", "--name", "pec-restore-check", "--no-deps", "-p", "127.0.0.1:8100:8099", "-e", "POSTGRES_DB=photography_events_restore_test", "photography-events-core")
        wait_ready(8100)
        assert check("/api/v1/opportunities/" + key, port=8100)["occurrence_key"] == key
        results["restore"] = "clean DB, extension, pg_restore, migrations, Core readiness and data passed"
    finally:
        (EVIDENCE / "acceptance.json").write_text(json.dumps(results, indent=2) + "\n")
        subprocess.run(["docker", "rm", "-f", "pec-restore-check"], check=False, capture_output=True)
        compose("down")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
