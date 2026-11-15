"""Expected sources and Expect Fallback Text (spec 14): a case's Expected sources (a Document and a
passage, with a Stale flag and its reason), Expect Fallback Text on the case and on a Run's copy of
it, the Run's copy of the Expected sources, and each Verdict's order among its result's.

Revision ID: 0046_evaluation_expectations
Revises: 0045_evaluation_run_in_progress
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_evaluation_expectations"
down_revision: str | None = "0045_evaluation_run_in_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_cases",
        sa.Column("expect_fallback", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "evaluation_run_cases",
        sa.Column("expect_fallback", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "evaluation_run_cases",
        sa.Column(
            "expected_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_verdicts",
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_table(
        "evaluation_expected_sources",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("passage", sa.Text(), nullable=False),
        sa.Column("stale", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stale_reason", sa.String(length=30), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["evaluation_cases.id"],
            name=op.f("fk_evaluation_expected_sources_case_id_evaluation_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_evaluation_expected_sources_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_expected_sources_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_expected_sources")),
    )
    for column in ("case_id", "document_id", "organisation_id"):
        op.create_index(
            op.f(f"ix_evaluation_expected_sources_{column}"),
            "evaluation_expected_sources",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("evaluation_expected_sources")
    op.drop_column("evaluation_verdicts", "position")
    op.drop_column("evaluation_run_cases", "expected_sources")
    op.drop_column("evaluation_run_cases", "expect_fallback")
    op.drop_column("evaluation_cases", "expect_fallback")
