"""Live Verdicts (spec 15): an Agent's Live sample rate among its Operational Settings, and the
Live Verdict of each sampled Visitor reply.

Revision ID: 0049_live_verdicts
Revises: 0048_evaluation_run_kind
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_live_verdicts"
down_revision: str | None = "0048_evaluation_run_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("live_sample_rate", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_table(
        "live_verdicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("grounded", sa.String(length=10), nullable=True),
        sa.Column("grounded_reason", sa.Text(), nullable=True),
        sa.Column("answers_question", sa.String(length=10), nullable=True),
        sa.Column("answers_question_reason", sa.Text(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("judge_provider", sa.String(length=50), nullable=True),
        sa.Column("judge_model", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_live_verdicts_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_live_verdicts_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_live_verdicts_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_live_verdicts_agent_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_live_verdicts")),
        sa.UniqueConstraint("message_id", name=op.f("uq_live_verdicts_message_id")),
    )
    op.create_index(op.f("ix_live_verdicts_organisation_id"), "live_verdicts", ["organisation_id"])
    op.create_index(op.f("ix_live_verdicts_agent_id"), "live_verdicts", ["agent_id"])
    op.create_index(
        op.f("ix_live_verdicts_agent_version_id"), "live_verdicts", ["agent_version_id"]
    )


def downgrade() -> None:
    op.drop_table("live_verdicts")
    op.drop_column("agents", "live_sample_rate")
