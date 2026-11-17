"""Suggestions (spec 16): a Suggestion's check, the Evaluation Run it started, and what the check
cost.

Revision ID: 0058_suggestion_check
Revises: 0057_suggestion_applied
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058_suggestion_check"
down_revision: str | None = "0057_suggestion_applied"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suggestions", sa.Column("check_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_suggestions_check_run_id_evaluation_runs"),
        "suggestions",
        "evaluation_runs",
        ["check_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_suggestions_check_run_id"), "suggestions", ["check_run_id"])
    op.add_column("suggestions", sa.Column("checking_cost_usd", sa.Numeric(18, 9), nullable=True))


def downgrade() -> None:
    op.drop_column("suggestions", "checking_cost_usd")
    op.drop_index(op.f("ix_suggestions_check_run_id"), table_name="suggestions")
    op.drop_constraint(
        op.f("fk_suggestions_check_run_id_evaluation_runs"), "suggestions", type_="foreignkey"
    )
    op.drop_column("suggestions", "check_run_id")
