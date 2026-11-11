"""The Organisation's Default Model.

Revision ID: 0008_default_models
Revises: 0007_provider_credentials
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_default_models"
down_revision: str | None = "0007_provider_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "default_models",
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
                name="fk_default_models_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            sa.Uuid(),
            sa.ForeignKey(
                "provider_credentials.id",
                name="fk_default_models_credential_id_provider_credentials",
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_default_models"),
        sa.UniqueConstraint("organisation_id", name="uq_default_models_organisation_id"),
    )
    op.create_index("ix_default_models_credential_id", "default_models", ["credential_id"])


def downgrade() -> None:
    op.drop_table("default_models")
