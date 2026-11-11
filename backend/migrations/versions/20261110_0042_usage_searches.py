"""Searches in metrics: each ``usage_daily`` row counts the Knowledge Searches its Version's
Visitor replies ran that day (``searches``), for mean searches per reply.

Revision ID: 0042_usage_searches
Revises: 0041_automatic_fallback
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_usage_searches"
down_revision: str | None = "0041_automatic_fallback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "usage_daily",
        sa.Column("searches", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("usage_daily", "searches")
