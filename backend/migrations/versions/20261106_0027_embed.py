"""Embedding: an Agent's Allowed Origins, the sites that may frame its widget; and the hash of
each Visitor Conversation's Conversation token.

Revision ID: 0027_embed
Revises: 0026_agent_versions
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_embed"
down_revision: str | None = "0026_agent_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "allowed_origins",
            postgresql.ARRAY(sa.String(length=255)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("conversations", sa.Column("token_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_conversations_token_hash", "conversations", ["token_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_conversations_token_hash", "conversations", type_="unique")
    op.drop_column("conversations", "token_hash")
    op.drop_column("agents", "allowed_origins")
