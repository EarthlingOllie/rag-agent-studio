"""Chunk quarantine: a Chunk the ingestion Guardrail scan flags is never retrieved unless an
Editor allows that one Chunk as a false positive (``chunks.guardrail_allowed_at`` and
``guardrail_allowed_by_id``). The per-Project Flagged Chunk mode is dropped: no setting lets a
detected prompt injection into the model's context.

Revision ID: 0043_chunk_quarantine
Revises: 0042_usage_searches
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_chunk_quarantine"
down_revision: str | None = "0042_usage_searches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("guardrail_allowed_at", sa.DateTime(timezone=True)))
    op.add_column("chunks", sa.Column("guardrail_allowed_by_id", sa.Uuid()))
    op.create_foreign_key(
        op.f("fk_chunks_guardrail_allowed_by_id_members"),
        "chunks",
        "members",
        ["guardrail_allowed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_chunks_guardrail_allowed_flagged"),
        "chunks",
        "guardrail_allowed_at IS NULL OR guardrail_label IS NOT NULL",
    )
    op.drop_constraint(op.f("ck_projects_flagged_chunk_mode"), "projects", type_="check")
    op.drop_column("projects", "flagged_chunk_mode")


def downgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "flagged_chunk_mode", sa.String(length=10), server_default="mark", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_projects_flagged_chunk_mode"),
        "projects",
        "flagged_chunk_mode IN ('mark', 'exclude')",
    )
    op.drop_constraint(op.f("ck_chunks_guardrail_allowed_flagged"), "chunks", type_="check")
    op.drop_constraint(
        op.f("fk_chunks_guardrail_allowed_by_id_members"), "chunks", type_="foreignkey"
    )
    op.drop_column("chunks", "guardrail_allowed_by_id")
    op.drop_column("chunks", "guardrail_allowed_at")
