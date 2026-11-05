"""Provider Credentials.

Revision ID: 0007_provider_credentials
Revises: 0007_themes
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_provider_credentials"
down_revision: str | None = "0007_themes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_provider_credentials_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("auth_kind", sa.String(32), nullable=False),
        sa.Column("secret_sealed", sa.LargeBinary(), nullable=False),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("masked_suffix", sa.String(8), nullable=False),
        sa.Column("capabilities", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("check_status", sa.String(16), nullable=False),
        sa.Column("check_failure", sa.String(32), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("secret_set_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organisation_id", "name", name="uq_provider_credentials_organisation_id"
        ),
    )
    op.create_index(
        "ix_provider_credentials_organisation_id", "provider_credentials", ["organisation_id"]
    )


def downgrade() -> None:
    op.drop_table("provider_credentials")
