"""Evaluation settings (spec 14): the Organisation's Evaluation Model (a Credential reference,
in the Default Model's shape) and Evaluation repeats, and the repeats each Evaluation Run copied
when it started. Runs before this answered each case once.

Revision ID: 0044_evaluation_settings
Revises: 0043_evaluation
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_evaluation_settings"
down_revision: str | None = "0043_evaluation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_evaluation_models_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            sa.Uuid(),
            sa.ForeignKey(
                "provider_credentials.id",
                name="fk_evaluation_models_credential_id_provider_credentials",
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_models"),
        sa.UniqueConstraint("organisation_id", name="uq_evaluation_models_organisation_id"),
    )
    op.create_index("ix_evaluation_models_credential_id", "evaluation_models", ["credential_id"])
    op.add_column(
        "organisations",
        sa.Column("evaluation_repeats", sa.Integer(), server_default=sa.text("3"), nullable=False),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("repeats", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "repeats")
    op.drop_column("organisations", "evaluation_repeats")
    op.drop_table("evaluation_models")
