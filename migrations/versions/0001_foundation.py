"""Foundation with deliberately reviewed PostGIS types, extension and indexes."""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Kept as readable SQL so reviewers can audit every spatial declaration.
    sql = Path(__file__).with_name("0001_schema.sql").read_text(encoding="utf-8")
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    op.execute("DROP VIEW source_health_current")
    for table in ("opportunity_context_evidence", "opportunity_observation_evidence", "opportunity_revisions",
                  "opportunities", "assessment_runs", "route_baselines", "phenomenon_locations",
                  "locations", "normalized_observations", "raw_observations", "source_backoff",
                  "source_runs", "source_roles", "sources"):
        op.execute(f"DROP TABLE {table}")
    # PostGIS belongs to the database, not to this application's downgrade.

