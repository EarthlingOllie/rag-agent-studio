"""The per-Agent Theme override: colour tokens that replace the Organisation Theme's for one
Agent's widget, and an avatar image. Not part of AgentConfig, so not versioned.

Revision ID: 0030_agent_theme_override
Revises: 0029_embed
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_agent_theme_override"
down_revision: str | None = "0029_embed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "theme_colours",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "agents", sa.Column("avatar", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agents", "avatar")
    op.drop_column("agents", "theme_colours")
