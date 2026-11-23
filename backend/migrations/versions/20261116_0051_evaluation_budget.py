"""The Evaluation budget (spec 15): an Organisation's monthly limit, in US dollars, on what its
Live Verdicts spend, and the spend record of each Organisation and calendar month (UTC).

Revision ID: 0051_evaluation_budget
Revises: 0050_live_verdicts_purged_at
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_evaluation_budget"
down_revision: str | None = "0050_live_verdicts_purged_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("evaluation_budget_usd", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.create_table(
        "evaluation_spend",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column(
            "spent_usd",
            sa.Numeric(precision=18, scale=9),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("budget_spent_emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "month"),
    )


def downgrade() -> None:
    op.drop_table("evaluation_spend")
    op.drop_column("organisations", "evaluation_budget_usd")
