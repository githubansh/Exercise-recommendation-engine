"""add plan versions

Revision ID: 0002_plan_versions
Revises: 0001_initial_schema
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_plan_versions"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE plans ADD COLUMN version INT")
    op.execute(
        """
        WITH ranked AS (
          SELECT id, row_number() OVER (PARTITION BY user_id, week_index ORDER BY id) AS plan_version
          FROM plans
        )
        UPDATE plans
        SET version = ranked.plan_version
        FROM ranked
        WHERE plans.id = ranked.id
        """
    )
    op.execute("ALTER TABLE plans ALTER COLUMN version SET DEFAULT 1")
    op.execute("ALTER TABLE plans ALTER COLUMN version SET NOT NULL")
    op.execute("CREATE INDEX ix_plans_user_week_version ON plans (user_id, week_index, version)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_plans_user_week_version")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS version")
