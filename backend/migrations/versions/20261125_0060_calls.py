"""Calls (spec 20): a Call record per Call, and Spoken Messages (``spoken`` and the Call they
were said in).

Revision ID: 0060_calls
Revises: 0059_call_settings
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060_calls"
down_revision: str | None = "0059_call_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_calls_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_calls_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_calls_agent_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calls")),
    )
    op.create_index(op.f("ix_calls_organisation_id"), "calls", ["organisation_id"])
    op.create_index(op.f("ix_calls_conversation_id"), "calls", ["conversation_id"])
    op.add_column(
        "messages",
        sa.Column("spoken", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("messages", sa.Column("call_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_messages_call_id_calls"),
        "messages",
        "calls",
        ["call_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_messages_call_id"), "messages", ["call_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_call_id"), table_name="messages")
    op.drop_constraint(op.f("fk_messages_call_id_calls"), "messages", type_="foreignkey")
    op.drop_column("messages", "call_id")
    op.drop_column("messages", "spoken")
    op.drop_index(op.f("ix_calls_conversation_id"), table_name="calls")
    op.drop_index(op.f("ix_calls_organisation_id"), table_name="calls")
    op.drop_table("calls")
