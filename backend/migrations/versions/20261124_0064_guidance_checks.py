"""Guidance checks (spec 19, ticket 19-04): guidance jobs, the Evaluation Model calls they make
with their Cost, and the latest check result kept on each Judging guidance version.

Revision ID: 0064_guidance_checks
Revises: 0063_judging_setup_reviews
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064_guidance_checks"
down_revision: str | None = "0063_judging_setup_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_COLUMNS = (
    "check_reviews",
    "check_agreed",
    "check_false_passes",
    "check_false_fails",
    "check_agreed_before",
)


def _count(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def upgrade() -> None:
    for column in _CHECK_COLUMNS:
        op.add_column("judging_guidance_versions", sa.Column(column, sa.Integer(), nullable=True))
    op.create_table(
        "guidance_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("judge_provider", sa.String(length=50), nullable=False),
        sa.Column("judge_model", sa.String(length=200), nullable=False),
        sa.Column("judging_guidance_version", sa.Integer(), nullable=True),
        sa.Column("held_out", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("other_half", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _count("judged"),
        _count("left_out"),
        _count("agreed"),
        _count("false_passes"),
        _count("false_fails"),
        _count("agreed_before"),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["members.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organisation_id", "judging_guidance_version"],
            ["judging_guidance_versions.organisation_id", "judging_guidance_versions.version"],
            name="fk_guidance_jobs_judging_guidance_version",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guidance_jobs_organisation_id", "guidance_jobs", ["organisation_id"])
    op.create_index("ix_guidance_jobs_requested_by", "guidance_jobs", ["requested_by"])
    op.create_index(
        "uq_guidance_jobs_in_progress",
        "guidance_jobs",
        ["organisation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "guidance_judgements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["guidance_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organisation_id", "job_id", "agent_id"):
        op.create_index(f"ix_guidance_judgements_{column}", "guidance_judgements", [column])


def downgrade() -> None:
    op.drop_table("guidance_judgements")
    op.drop_table("guidance_jobs")
    for column in _CHECK_COLUMNS:
        op.drop_column("judging_guidance_versions", column)
