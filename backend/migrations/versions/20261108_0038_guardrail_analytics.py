"""Guardrail analytics and alerts: each ``usage_daily`` row counts the replies the input
Guardrail blocked (the block rate), and an Agent carries its Block rate alert flag, raised by
the hourly rollup when its block rate spikes.

Revision ID: 0038_guardrail_analytics
Revises: 0037_usage_daily
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_guardrail_analytics"
down_revision: str | None = "0037_usage_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "usage_daily",
        sa.Column("guardrail_blocks", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "agents", sa.Column("block_rate_alert_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agents", "block_rate_alert_at")
    op.drop_column("usage_daily", "guardrail_blocks")
