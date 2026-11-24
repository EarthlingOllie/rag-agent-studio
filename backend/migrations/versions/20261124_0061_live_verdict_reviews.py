"""Verdict reviews of Live Verdict checks (spec 18, ticket 18-03): a review targets a Run
Verdict, or a Live Verdict and its check (unique per pair), and carries a purged-at stamp.

Revision ID: 0061_live_verdict_reviews
Revises: 0060_judging_guidance
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_live_verdict_reviews"
down_revision: str | None = "0060_judging_guidance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("verdict_reviews", "verdict_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("verdict_reviews", sa.Column("live_verdict_id", sa.Uuid(), nullable=True))
    op.add_column(
        "verdict_reviews", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_verdict_reviews_live_verdict_id_live_verdicts"),
        "verdict_reviews",
        "live_verdicts",
        ["live_verdict_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_verdict_reviews_live_verdict_id"), "verdict_reviews", ["live_verdict_id", "check"]
    )
    op.create_check_constraint(
        op.f("ck_verdict_reviews_one_target"),
        "verdict_reviews",
        "(verdict_id IS NULL) <> (live_verdict_id IS NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM verdict_reviews WHERE live_verdict_id IS NOT NULL")
    op.drop_constraint(op.f("ck_verdict_reviews_one_target"), "verdict_reviews", type_="check")
    op.drop_constraint(
        op.f("uq_verdict_reviews_live_verdict_id"), "verdict_reviews", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_verdict_reviews_live_verdict_id_live_verdicts"),
        "verdict_reviews",
        type_="foreignkey",
    )
    op.drop_column("verdict_reviews", "purged_at")
    op.drop_column("verdict_reviews", "live_verdict_id")
    op.alter_column("verdict_reviews", "verdict_id", existing_type=sa.Uuid(), nullable=False)
