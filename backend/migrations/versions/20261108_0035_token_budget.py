"""The Token Budget: how many tokens an Agent's Visitor replies may use per UTC date
(Operational Settings), and the alert flag raised when it runs out.

Revision ID: 0035_token_budget
Revises: 0034_rate_limits
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_token_budget"
down_revision: str | None = "0034_rate_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "daily_token_budget", sa.Integer(), server_default=sa.text("1000000"), nullable=False
        ),
    )
    op.add_column(
        "agents", sa.Column("budget_exhausted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agents", "budget_exhausted_at")
    op.drop_column("agents", "daily_token_budget")
