"""Two-sided Evaluation Runs (spec 14): an Agent has at most one queued or running Run, enforced
with a partial unique index (Runs may now also be ``cancelled``).

Revision ID: 0045_evaluation_run_in_progress
Revises: 0044_evaluation_settings
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_evaluation_run_in_progress"
down_revision: str | None = "0044_evaluation_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_evaluation_runs_in_progress_agent",
        "evaluation_runs",
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_evaluation_runs_in_progress_agent", table_name="evaluation_runs")
