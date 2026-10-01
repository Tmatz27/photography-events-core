"""Fail closed on migration error without printing DB URLs or bind parameters."""
import os
import sys

from alembic import command
from alembic.config import Config

from pec.logging import event

try:
    command.upgrade(Config("alembic.ini"), "head")
except Exception:
    event("schema_issue", code="startup_migration_failed")
    sys.exit(1)
os.execvp("python", ["python", "-m", "uvicorn", "pec.api:create_app", "--factory",
                      "--host", "0.0.0.0", "--port", "8099", "--no-access-log"])
