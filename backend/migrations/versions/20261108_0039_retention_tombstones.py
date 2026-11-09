"""Retention and tombstones: the Organisation's Retention Window (``retention_days``, default
90), when a Message's text was purged (``messages.purged_at``), when a Conversation was deleted
on request (``conversations.deleted_at``), and each Message retrieval's Document-name snapshot
(``message_retrievals.document_name``, the tombstone), with its Chunk and Document IDs nullable
so they can be cleared when the Document is deleted.

Revision ID: 0039_retention_tombstones
Revises: 0038_guardrail_analytics
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_retention_tombstones"
down_revision: str | None = "0038_guardrail_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("retention_days", sa.Integer(), server_default=sa.text("90"), nullable=False),
    )
    op.add_column("messages", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    # The purge looks for Messages not yet purged, oldest first.
    op.create_index(
        "ix_messages_unpurged_created_at",
        "messages",
        ["created_at"],
        postgresql_where=sa.text("purged_at IS NULL"),
    )
    op.add_column(
        "conversations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("message_retrievals", sa.Column("document_name", sa.Text(), nullable=True))
    # Retrievals of Documents that still exist get their name; those of Documents deleted
    # before this migration have no name to keep.
    op.execute(
        "UPDATE message_retrievals AS r SET document_name = d.name "
        "FROM documents AS d WHERE d.id = r.document_id"
    )
    op.execute(
        "UPDATE message_retrievals SET document_id = NULL, chunk_id = NULL "
        "WHERE document_name IS NULL"
    )
    op.alter_column("message_retrievals", "chunk_id", nullable=True)
    op.alter_column("message_retrievals", "document_id", nullable=True)
    op.create_index("ix_message_retrievals_document_id", "message_retrievals", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_message_retrievals_document_id", table_name="message_retrievals")
    # Tombstones have no IDs to go back to.
    op.execute("DELETE FROM message_retrievals WHERE document_id IS NULL OR chunk_id IS NULL")
    op.alter_column("message_retrievals", "document_id", nullable=False)
    op.alter_column("message_retrievals", "chunk_id", nullable=False)
    op.drop_column("message_retrievals", "document_name")
    op.drop_column("conversations", "deleted_at")
    op.drop_index("ix_messages_unpurged_created_at", table_name="messages")
    op.drop_column("messages", "purged_at")
    op.drop_column("organisations", "retention_days")
