"""Agents with their Drafts, and Conversations with their Messages.

Revision ID: 0012_agents_conversations
Revises: 0011_documents
Create Date: 2026-11-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_agents_conversations"
down_revision: str | None = "0011_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _foreign(table: str, column: str, target: str) -> sa.Column[Any]:
    return sa.Column(
        column,
        sa.Uuid(),
        sa.ForeignKey(f"{target}.id", ondelete="CASCADE", name=f"fk_{table}_{column}_{target}"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        _foreign("agents", "organisation_id", "organisations"),
        _foreign("agents", "project_id", "projects"),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("public_id", name="uq_agents_public_id"),
    )
    for column in ("organisation_id", "project_id"):
        op.create_index(f"ix_agents_{column}", "agents", [column])

    op.create_table(
        "agent_drafts",
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="CASCADE", name="fk_agent_drafts_agent_id_agents"),
            primary_key=True,
        ),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        _foreign("conversations", "organisation_id", "organisations"),
        _foreign("conversations", "agent_id", "agents"),
        sa.Column("is_playground", sa.Boolean(), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    for column in ("organisation_id", "agent_id"):
        op.create_index(f"ix_conversations_{column}", "conversations", [column])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        _foreign("messages", "organisation_id", "organisations"),
        _foreign("messages", "conversation_id", "conversations"),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("config_source", sa.String(40), nullable=True),
        sa.Column("model_provider", sa.String(40), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("first_token_ms", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 9), nullable=True),
        sa.UniqueConstraint("seq", name="uq_messages_seq"),
    )
    for column in ("organisation_id", "conversation_id"):
        op.create_index(f"ix_messages_{column}", "messages", [column])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("agent_drafts")
    op.drop_table("agents")
