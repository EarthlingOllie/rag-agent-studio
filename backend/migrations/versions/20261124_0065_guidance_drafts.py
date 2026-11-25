"""Guidance drafts (spec 19, ticket 19-05): a draft guidance job's reviews read, its drafted text
and its explanation.

Revision ID: 0065_guidance_drafts
Revises: 0064_guidance_checks
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065_guidance_drafts"
down_revision: str | None = "0064_guidance_checks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "guidance_jobs",
        sa.Column("reviews_read", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("guidance_jobs", sa.Column("draft_text", sa.Text(), nullable=True))
    op.add_column(
        "guidance_jobs",
        sa.Column("draft_explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guidance_jobs", "draft_explanation")
    op.drop_column("guidance_jobs", "draft_text")
    op.drop_column("guidance_jobs", "reviews_read")
