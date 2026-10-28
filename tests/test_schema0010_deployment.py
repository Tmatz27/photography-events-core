"""Deployment evidence tools may never target the installed application DB."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "upgrade_check", Path(__file__).parents[1] / "tools/verify_schema0010_upgrade.py"
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


@pytest.mark.parametrize(
    "url,ci",
    [
        ("postgresql+asyncpg://unused@localhost/photography_events", "true"),
        ("postgresql+asyncpg://unused@localhost/photography_events_test", "false"),
        ("postgresql://unused@localhost/photography_events_test", "true"),
    ],
)
def test_upgrade_verification_rejects_installed_or_non_ci_database(url, ci):
    with pytest.raises(ValueError):
        upgrade.require_disposable(url, ci)


def test_upgrade_verification_accepts_only_explicit_disposable_ci_target():
    upgrade.require_disposable("postgresql+asyncpg://unused@localhost/photography_events_test", "true")
    with pytest.raises(ValueError):
        upgrade.quoted("source_runs; DROP SCHEMA public")
