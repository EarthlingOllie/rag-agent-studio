"""Scheduled jobs catch up (spec 21): an Agent records the last hour its Block rate alert check
covered, so the next run checks every hour since.

Revision ID: 0068_block_rate_checked_at
Revises: 0067_call_rollups
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068_block_rate_checked_at"
down_revision: str | None = "0067_call_rollups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents", sa.Column("block_rate_checked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agents", "block_rate_checked_at")
