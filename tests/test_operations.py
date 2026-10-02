"""Deployment boundary and destructive-restore guard contracts."""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_production_network_and_postgres18_volume_contract():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]
    assert set(services) == {"photography-events-db", "photography-events-core"}
    db = services["photography-events-db"]
    assert db["image"] == "postgis/postgis:18-3.6"
    assert not db.get("ports")
    assert db["networks"] == ["database"]
    assert compose["networks"]["database"]["internal"] is True
    assert db["volumes"][0].endswith(":/var/lib/postgresql")
    core = services["photography-events-core"]
    assert core["build"]["target"] == "runtime"
    assert "POSTGRES_ADMIN_PASSWORD" not in core["environment"]
    assert not core.get("devices")
    assert "127.0.0.1" in core["ports"][0]


@pytest.mark.skipif(os.name == "nt", reason="Operator script runs on Unraid/Linux; exercised by Docker CI")
@pytest.mark.parametrize("name", ["photography_events", "postgres", "bad;name", "../path"])
def test_restore_refuses_unsafe_destination_before_any_docker_call(name):
    result = subprocess.run(["sh", "scripts/restore.sh", "/does-not-exist.dump", name], cwd=ROOT, capture_output=True)
    assert result.returncode == 2
    assert b"Unsafe target database name" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="Operator script requires POSIX shell")
def test_n8_failed_dump_removes_partial_archive(tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nprintf 'partial backup'\nexit 1\n")
    docker.chmod(0o700)
    destination = tmp_path / "backups"
    result = subprocess.run(["sh", "scripts/backup.sh"], cwd=ROOT, capture_output=True,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "BACKUP_DIR": str(destination)})
    assert result.returncode != 0
    assert list(destination.iterdir()) == []
