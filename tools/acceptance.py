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
        assert results["startup"]["schema_version"] == "0007"
        results["fresh_database_to_0007"] = "passed"
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
        compose(*test_exec, "-m", "alembic", "upgrade", "0003")
        compose(*test_exec, "tools/migration_acceptance.py", "seed-shadow")
        compose(*test_exec, "-m", "alembic", "upgrade", "0004")
        compose(*test_exec, "tools/migration_acceptance.py", "seed-final")
        compose(*test_exec, "-m", "alembic", "upgrade", "head")
        compose(*test_exec, "tools/migration_acceptance.py", "verify")
        results["R20_migration_0001_to_0002"] = "identity and provider data preserved; API reads held legacy context"
        results["migration_0001_0002_0003_0004_0005_0006_0007"] = "identity, memberships, behavior and held API verified"
        results["migration_0003_0004_shadow_history"] = "existing run hashes/timestamps preserved with published lifecycle"
        compose(*test_exec, "-m", "alembic", "upgrade", "head")
        results["repeat_migration"] = "passed"
        compose("cp",str(EVIDENCE / "collection-baselines"),"photography-events-core:/tmp/collection-baselines")
        try:
            compose(*test_exec,"tools/h3_acceptance.py")
        finally:
            compose("cp","photography-events-core:/tmp/h3-performance.json",str(EVIDENCE / "h3-performance.json"))
        with (EVIDENCE / "pytest.log").open("w") as log:
            try:
                compose(*test_exec, "tools/database_tests.py", stdout=log, stderr=subprocess.STDOUT)
            finally:
                compose("cp", "photography-events-core:/tmp/core-tests.xml", str(EVIDENCE / "tests.xml"))
        results["migration_0002_downgrade"] = "forward-only; restore pre-upgrade backup instead of losing history"
        compose("cp",str(EVIDENCE / "collection-baselines"),"photography-events-core:/tmp/collection-baselines")
        compose(*test_exec,"tools/collection_benchmark.py")
        compose("cp","photography-events-core:/tmp/collection-performance.json",str(EVIDENCE / "collection-performance.json"))
        compose("exec", "-T", "photography-events-core", "python", "-m", "pec", "tests/fixtures/legacy_tule_elk.json")
        key = "tule_elk_rut-2026-09-15"
        first = check("/api/v1/opportunities/" + key)
        results["fixture_readable"] = first["occurrence_key"]
        compose("exec", "-T", "photography-events-core", "python", "tools/m2_acceptance.py")
        compose("cp", "photography-events-core:/tmp/m2-performance.json", str(EVIDENCE / "m2-performance.json"))
        patterns = check("/api/v1/debug/patterns")
        assert len(patterns["items"]) == 1 and not patterns["preview_opportunities"]
        episode_key = patterns["items"][0]["episode_key"]
        results["M2_shadow_1000_reports"] = "one episode; zero promoted opportunities"
        check("/api/v1/opportunities", 401, token=False)
        results["bad_token"] = "401"
        compose("restart", "photography-events-core")
        wait_ready()
        assert check("/api/v1/opportunities/" + key)["occurrence_key"] == key
        results["core_restart"] = "data preserved"
        assert check("/api/v1/debug/patterns")["items"][0]["episode_key"] == episode_key
        results["M2_core_restart"] = "episode identity preserved"
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
        assert check("/api/v1/debug/patterns")["items"][0]["episode_key"] == episode_key
        results["M2_database_restart"] = "episode identity preserved"
        # Execute the operator scripts themselves, not merely equivalent commands.
        backup_result = run("sh", "scripts/backup.sh", env={**os.environ, "BACKUP_DIR": str(EVIDENCE / "backups")},
                            capture_output=True, text=True)
        backup = Path(backup_result.stdout.strip())
        before_restore=check("/api/v1/debug/patterns")
        identity_sql="""SELECT md5(COALESCE(string_agg(concat_ws('|',m.id,m.report_group_id,
            m.normalized_observation_id,m.link_basis,m.created_at,m.superseded_at,
            g.origin_namespace,g.origin_external_id),',' ORDER BY m.id),''))
            FROM observation_report_group_members m JOIN observation_report_groups g ON g.id=m.report_group_id"""
        before_identity=compose("exec","-T","photography-events-db","psql","-U","postgres",
            "-d","photography_events","-Atc",identity_sql,capture_output=True,text=True).stdout.strip()
        assert backup.read_bytes()[:5] == b"PGDMP"
        results["backup_bytes"] = backup.stat().st_size
        run("sh", "scripts/restore.sh", str(backup), "photography_events_restore_test")
        results["operator_scripts"] = "backup.sh and restore.sh executed successfully"
        owners = compose("exec", "-T", "photography-events-db", "psql", "-U", "postgres", "-d", "photography_events_restore_test", "-Atc",
            "SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='opportunities'", capture_output=True, text=True).stdout.strip()
        assert owners == "photography_events", owners
        results["restored_application_owner"] = owners
        m2_owners=compose("exec","-T","photography-events-db","psql","-U","postgres",
            "-d","photography_events_restore_test","-Atc","""SELECT DISTINCT tableowner FROM pg_tables
            WHERE schemaname='public' AND tablename IN
            ('observation_report_groups','observation_report_group_members','pattern_episodes','normalized_observations')""",
            capture_output=True,text=True).stdout.strip()
        assert m2_owners=="photography_events",m2_owners
        restored_indexes=compose("exec","-T","photography-events-db","psql","-U","postgres",
            "-d","photography_events_restore_test","-Atc","""SELECT count(*) FROM pg_indexes
            WHERE schemaname='public' AND indexname IN
            ('ix_raw_local_report_identity','ix_raw_explicit_origin','ix_normalized_superseded_raw')""",
            capture_output=True,text=True).stdout.strip()
        assert restored_indexes=="3",restored_indexes
        results["restored_h3_indexes"]="all three 0006 indexes present"
        restored_identity=compose("exec","-T","photography-events-db","psql","-U","postgres",
            "-d","photography_events_restore_test","-Atc",identity_sql,capture_output=True,text=True).stdout.strip()
        assert restored_identity==before_identity
        results["restored_report_group_identity"]="exact current/historical membership digest preserved"
        # Same Core service image and app user, fresh container pointed at restored DB.
        compose("run", "-d", "--name", "pec-restore-check", "--no-deps", "-p", "127.0.0.1:8100:8099", "-e", "POSTGRES_DB=photography_events_restore_test", "photography-events-core")
        restored_ready=wait_ready(8100)
        assert restored_ready["schema_version"]=="0007"
        assert check("/api/v1/opportunities/" + key, port=8100)["occurrence_key"] == key
        restored_debug=check("/api/v1/debug/patterns", port=8100)
        assert restored_debug["items"][0]["episode_key"] == episode_key
        assert restored_debug["mode"]==before_restore["mode"]
        assert restored_debug["analysis_state"]==before_restore["analysis_state"]
        assert restored_debug["items"][0]["state"]==before_restore["items"][0]["state"]
        results["restored_migration_head"]=restored_ready["schema_version"]
        results["restored_m2_debug_state"]=restored_debug["analysis_state"]
        results["M2_restore"] = "episode identity and generation artifacts preserved"
        results["restore"] = "clean DB, extension, pg_restore, migrations, Core readiness and data passed"
    finally:
        (EVIDENCE / "acceptance.json").write_text(json.dumps(results, indent=2) + "\n")
        subprocess.run(["docker", "rm", "-f", "pec-restore-check"], check=False, capture_output=True)
        compose("down")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
