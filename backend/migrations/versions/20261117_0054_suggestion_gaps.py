"""Suggestions (spec 16): every kind of evidence, and Knowledge Base gaps.

A piece of evidence keeps every kind it qualifies as, and points at a Visitor reply or at an
Evaluation Case as its Run copied it. Knowledge Base gaps are a Suggestion's own table.

Revision ID: 0054_suggestion_gaps
Revises: 0053_suggestions
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_suggestion_gaps"
down_revision: str | None = "0053_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "suggestion_evidence",
        sa.Column(
            "kinds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute("UPDATE suggestion_evidence SET kinds = jsonb_build_array(kind)")
    op.alter_column("suggestion_evidence", "kinds", server_default=None)
    op.alter_column("suggestion_evidence", "message_id", nullable=True)
    op.add_column("suggestion_evidence", sa.Column("run_case_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_suggestion_evidence_run_case_id_evaluation_run_cases"),
        "suggestion_evidence",
        "evaluation_run_cases",
        ["run_case_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_suggestion_evidence_run_case_id"), "suggestion_evidence", ["run_case_id"]
    )

    op.create_table(
        "suggestion_gaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_suggestion_gaps_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suggestion_id"],
            ["suggestions.id"],
            name=op.f("fk_suggestion_gaps_suggestion_id_suggestions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suggestion_gaps")),
    )
    for column in ("organisation_id", "suggestion_id"):
        op.create_index(op.f(f"ix_suggestion_gaps_{column}"), "suggestion_gaps", [column])


def downgrade() -> None:
    op.drop_table("suggestion_gaps")
    op.execute("DELETE FROM suggestion_evidence WHERE message_id IS NULL")
    op.drop_index(op.f("ix_suggestion_evidence_run_case_id"), table_name="suggestion_evidence")
    op.drop_constraint(
        op.f("fk_suggestion_evidence_run_case_id_evaluation_run_cases"),
        "suggestion_evidence",
        type_="foreignkey",
    )
    op.drop_column("suggestion_evidence", "run_case_id")
    op.alter_column("suggestion_evidence", "message_id", nullable=False)
    op.drop_column("suggestion_evidence", "kinds")
