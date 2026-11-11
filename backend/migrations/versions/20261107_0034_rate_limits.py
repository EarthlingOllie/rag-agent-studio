"""Rate limits: how many Visitor messages an Agent admits in any minute per Conversation and
per IP address (Operational Settings).

Revision ID: 0034_rate_limits
Revises: 0033_flagged_chunk_mode
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_rate_limits"
down_revision: str | None = "0033_flagged_chunk_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "conversation_messages_per_minute",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=False,
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "ip_messages_per_minute", sa.Integer(), server_default=sa.text("30"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "ip_messages_per_minute")
    op.drop_column("agents", "conversation_messages_per_minute")
