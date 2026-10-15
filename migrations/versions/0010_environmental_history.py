"""Typed environmental history independent of biological analysis."""

from pathlib import Path
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    for statement in Path(__file__).with_suffix(".sql").read_text().split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("0010 is forward-only; restore a verified backup to a new database")
