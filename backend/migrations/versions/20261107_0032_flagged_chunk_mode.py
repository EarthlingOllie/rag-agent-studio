"""Flagged Chunk mode: whether a Project's Chunks the ingestion Guardrail scan flags are only
marked (still retrieved) or excluded from retrieval. Every existing Project marks them, as
before.

Revision ID: 0032_flagged_chunk_mode
Revises: 0031_operational_settings
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_flagged_chunk_mode"
down_revision: str | None = "0031_operational_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "flagged_chunk_mode", sa.String(length=10), nullable=False, server_default="mark"
        ),
    )
    op.create_check_constraint(
        op.f("ck_projects_flagged_chunk_mode"),
        "projects",
        "flagged_chunk_mode IN ('mark', 'exclude')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_projects_flagged_chunk_mode"), "projects", type_="check")
    op.drop_column("projects", "flagged_chunk_mode")
