"""Run Cost (spec 14): a Run's estimated Cost, stored when it starts, and each case result's judging
Cost beside its answer's.

Revision ID: 0047_evaluation_run_cost
Revises: 0046_evaluation_expectations
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_evaluation_run_cost"
down_revision: str | None = "0046_evaluation_expectations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("estimated_cost_usd", sa.Numeric(precision=18, scale=9), nullable=True),
    )
    op.add_column(
        "evaluation_case_results",
        sa.Column("judge_cost_usd", sa.Numeric(precision=18, scale=9), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_case_results", "judge_cost_usd")
    op.drop_column("evaluation_runs", "estimated_cost_usd")
