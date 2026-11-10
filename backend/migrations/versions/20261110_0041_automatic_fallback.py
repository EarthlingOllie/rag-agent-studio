"""The Automatic fallback: ``messages.automatic_fallback``, true for an answer of an Agentic
Agent that ran as Automatic because its chat model can't use tools.

Revision ID: 0041_automatic_fallback
Revises: 0040_searches
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_automatic_fallback"
down_revision: str | None = "0040_searches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("automatic_fallback", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("messages", "automatic_fallback")
