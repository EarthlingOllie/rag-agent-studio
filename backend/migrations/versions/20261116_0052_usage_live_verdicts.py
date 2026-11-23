"""Live score (spec 15): each ``usage_daily`` row counts its Version's Live Verdicts judged and
passed, by the day of the reply (``live_judged``, ``live_passed``).

Revision ID: 0052_usage_live_verdicts
Revises: 0051_evaluation_budget
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_usage_live_verdicts"
down_revision: str | None = "0051_evaluation_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("live_judged", "live_passed"):
        op.add_column(
            "usage_daily",
            sa.Column(column, sa.Integer(), server_default=sa.text("0"), nullable=False),
        )


def downgrade() -> None:
    op.drop_column("usage_daily", "live_passed")
    op.drop_column("usage_daily", "live_judged")
