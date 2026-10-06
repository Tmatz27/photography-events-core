"""CI-only test entry point. Keep the ephemeral DB secret out of process argv."""
import os

import pytest

from pec.config import Settings

settings = Settings.from_env()
os.environ["CORE_TEST_DATABASE_URL"] = settings.database_url.render_as_string(hide_password=False)
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "-o", "junit_family=legacy",
                             "--junitxml=/tmp/core-tests.xml"]))
