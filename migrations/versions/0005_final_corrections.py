"""Server-bound shadow publication diagnostics and legacy behavior correction."""
from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    sql=Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    sql="\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("0005 is forward-only; restore a verified pre-upgrade backup to a new database")
