"""Suggestions (spec 16): who applied a Suggestion to the Draft, and when.

Revision ID: 0057_suggestion_applied
Revises: 0056_suggestion_run_cost
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057_suggestion_applied"
down_revision: str | None = "0056_suggestion_run_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suggestions", sa.Column("applied_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_suggestions_applied_by_members"),
        "suggestions",
        "members",
        ["applied_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("suggestions", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("suggestions", "applied_at")
    op.drop_constraint(op.f("fk_suggestions_applied_by_members"), "suggestions", type_="foreignkey")
    op.drop_column("suggestions", "applied_by")
