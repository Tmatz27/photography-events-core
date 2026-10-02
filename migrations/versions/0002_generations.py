"""Immutable generations and corrected current assertions; preserve 0001 data."""
from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL truncates automatically generated constraint names. Discover
    # the old uniqueness constraint rather than guessing its truncated spelling.
    op.execute("""DO $$ DECLARE c RECORD; BEGIN
      FOR c IN SELECT conname FROM pg_constraint
        WHERE conrelid='normalized_observations'::regclass AND contype='u'
      LOOP EXECUTE format('ALTER TABLE normalized_observations DROP CONSTRAINT %I', c.conname);
      END LOOP;
    END $$""")
    sql = Path(__file__).with_name("0002_generations.sql").read_text(encoding="utf-8")
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    # 0001 cannot represent historical generations or corrected assertions.
    # A silent lossy collapse would undo the integrity guarantee this migration adds.
    raise RuntimeError("0002 is forward-only; restore a verified pre-upgrade backup to a new database")
