"""Verdict reviews (spec 18): an Editor's own pass or fail on a judged Run Verdict.

Revision ID: 0059_verdict_reviews
Revises: 0058_suggestion_check
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_verdict_reviews"
down_revision: str | None = "0058_suggestion_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verdict_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("verdict_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("evaluation_model_outcome", sa.String(10), nullable=False),
        sa.Column("check", sa.String(30), nullable=False),
        sa.Column("judge_provider", sa.String(50), nullable=False),
        sa.Column("judge_model", sa.String(200), nullable=False),
        sa.Column("from_sample", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_verdict_reviews_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_verdict_reviews_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verdict_id"],
            ["evaluation_verdicts.id"],
            name=op.f("fk_verdict_reviews_verdict_id_evaluation_verdicts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["members.id"],
            name=op.f("fk_verdict_reviews_reviewed_by_members"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verdict_reviews")),
        sa.UniqueConstraint("verdict_id", name=op.f("uq_verdict_reviews_verdict_id")),
    )
    op.create_index(
        op.f("ix_verdict_reviews_organisation_id"), "verdict_reviews", ["organisation_id"]
    )
    op.create_index(op.f("ix_verdict_reviews_agent_id"), "verdict_reviews", ["agent_id"])
    op.create_index(op.f("ix_verdict_reviews_reviewed_by"), "verdict_reviews", ["reviewed_by"])


def downgrade() -> None:
    op.drop_table("verdict_reviews")
