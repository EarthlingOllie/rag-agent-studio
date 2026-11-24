"""Review sample skips (spec 18, ticket 18-05): each item an Editor skipped, counted against the
Evaluation Model judging then, so the agreement card shows the skip count.

Revision ID: 0062_review_sample_skips
Revises: 0061_live_verdict_reviews
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_review_sample_skips"
down_revision: str | None = "0061_live_verdict_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_sample_skips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("judge_provider", sa.String(50), nullable=False),
        sa.Column("judge_model", sa.String(200), nullable=False),
        sa.Column("skipped_by", sa.Uuid(), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_review_sample_skips_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skipped_by"],
            ["members.id"],
            name=op.f("fk_review_sample_skips_skipped_by_members"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_sample_skips")),
    )
    op.create_index(
        op.f("ix_review_sample_skips_organisation_id"), "review_sample_skips", ["organisation_id"]
    )
    op.create_index(
        op.f("ix_review_sample_skips_skipped_by"), "review_sample_skips", ["skipped_by"]
    )


def downgrade() -> None:
    op.drop_table("review_sample_skips")
