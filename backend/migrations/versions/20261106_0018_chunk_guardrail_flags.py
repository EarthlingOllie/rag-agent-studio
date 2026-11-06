"""Chunk Guardrail flags: the injection classifier's label, score and reason, set on Chunks the
ingestion scan flags.

Revision ID: 0018_chunk_guardrail_flags
Revises: 0017_message_retrievals
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_chunk_guardrail_flags"
down_revision: str | None = "0017_message_retrievals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("guardrail_label", sa.String(length=50), nullable=True))
    op.add_column("chunks", sa.Column("guardrail_score", sa.Float(), nullable=True))
    op.add_column("chunks", sa.Column("guardrail_reason", sa.Text(), nullable=True))
    # A flag has all three, or the Chunk has none.
    op.create_check_constraint(
        op.f("ck_chunks_guardrail_flag_complete"),
        "chunks",
        "(guardrail_label IS NULL) = (guardrail_score IS NULL)"
        " AND (guardrail_label IS NULL) = (guardrail_reason IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_chunks_guardrail_flag_complete"), "chunks", type_="check")
    op.drop_column("chunks", "guardrail_reason")
    op.drop_column("chunks", "guardrail_score")
    op.drop_column("chunks", "guardrail_label")
