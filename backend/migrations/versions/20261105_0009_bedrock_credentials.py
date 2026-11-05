"""Bedrock credentials: IAM role credentials hold no secret, and each Organisation gets an
external ID for its role trust policies.

Revision ID: 0009_bedrock_credentials
Revises: 0008_default_models
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_bedrock_credentials"
down_revision: str | None = "0008_default_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("provider_credentials", "secret_sealed", nullable=True)
    op.alter_column("provider_credentials", "masked_suffix", nullable=True)
    op.add_column("provider_credentials", sa.Column("role_arn", sa.String(2048), nullable=True))
    op.create_table(
        "aws_external_ids",
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_aws_external_ids_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organisation_id", name="pk_aws_external_ids"),
        sa.UniqueConstraint("external_id", name="uq_aws_external_ids_external_id"),
    )


def downgrade() -> None:
    op.drop_table("aws_external_ids")
    # Credentials without a secret (Bedrock IAM roles) can't exist before this revision.
    op.execute("DELETE FROM provider_credentials WHERE secret_sealed IS NULL")
    op.drop_column("provider_credentials", "role_arn")
    op.alter_column("provider_credentials", "masked_suffix", nullable=False)
    op.alter_column("provider_credentials", "secret_sealed", nullable=False)
