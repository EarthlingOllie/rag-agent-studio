"""Message retrievals: each Chunk retrieval found for an answer, for the Trace, and whether
the answer was the fallback text.

Revision ID: 0017_message_retrievals
Revises: 0016_project_ocr
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_message_retrievals"
down_revision: str | None = "0016_project_ocr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("fallback", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "message_retrievals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_message_retrievals_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey(
                "messages.id", ondelete="CASCADE", name="fk_message_retrievals_message_id_messages"
            ),
            nullable=False,
        ),
        # No foreign keys: the Trace outlives a Chunk replaced or deleted with its Document.
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("cited", sa.Boolean(), nullable=False),
        sa.Column("excluded_reason", sa.String(40), nullable=True),
        sa.UniqueConstraint("message_id", "position", name="uq_message_retrievals_message_id"),
    )
    op.create_index(
        "ix_message_retrievals_organisation_id", "message_retrievals", ["organisation_id"]
    )


def downgrade() -> None:
    op.drop_table("message_retrievals")
    op.drop_column("messages", "fallback")
