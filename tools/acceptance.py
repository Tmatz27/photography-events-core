"""Real Docker/PostGIS restart and custom-format restore acceptance.

Run only in a disposable checkout. Artifacts contain no secrets. This script
does not touch an Unraid host or production NAS.
"""
import json
import os
import secrets
import subprocess
import sys
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
        url = f"postgresql+asyncpg://photography_events:{os.environ['POSTGRES_PASSWORD']}@127.0.0.1:54329/photography_events_test"
        env = {**os.environ, "CORE_DATABASE_URL": url, "CORE_TEST_DATABASE_URL": url}
        run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
        run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
        results["repeat_migration"] = "passed"
        with (EVIDENCE / "pytest.log").open("w") as log:
            run(sys.executable, "-m", "pytest", "-q", "--junitxml=evidence/tests.xml", env=env, stdout=log, stderr=subprocess.STDOUT)
        # Test a full downgrade/upgrade only against the disposable test DB.
        run(sys.executable, "-m", "alembic", "downgrade", "base", env=env)
        run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
        results["migration_round_trip"] = "passed"
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
        compose("stop", "photography-events-db")
        check("/health/live")
        check("/health/ready", 503)
        check("/api/v1/opportunities", 503)
        results["database_stopped"] = "live 200, ready 503, data 503"
        compose("start", "photography-events-db")
        wait_ready()
        assert check("/api/v1/opportunities/" + key)["occurrence_key"] == key
        results["database_restart"] = "ready and data preserved"
        backup = EVIDENCE / "acceptance.dump"
        with backup.open("wb") as out:
            compose("exec", "-T", "photography-events-db", "pg_dump", "-U", "postgres", "-d", "photography_events", "-Fc", "--no-owner", "--no-acl", stdout=out)
        assert backup.read_bytes()[:5] == b"PGDMP"
        results["backup_bytes"] = backup.stat().st_size
        compose("exec", "-T", "photography-events-db", "createdb", "-U", "postgres", "-O", "photography_events", "photography_events_restore_test")
        compose("exec", "-T", "photography-events-db", "psql", "-U", "postgres", "-d", "photography_events_restore_test", "-c", "CREATE EXTENSION postgis")
        with backup.open("rb") as source:
            compose("exec", "-T", "photography-events-db", "pg_restore", "-U", "postgres", "--role=photography_events", "-d", "photography_events_restore_test", "--no-owner", "--no-acl", "--no-comments", "--exit-on-error", stdin=source)
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
