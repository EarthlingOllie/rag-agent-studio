"""The platform price table and per-credential price overrides.

The rows of ``model_prices`` are not written here: ``migrations/env.py`` reloads them from
``app/pricing/price_table.json`` after every upgrade, so editing that file and migrating is
enough to change prices.

Revision ID: 0010_price_table
Revises: 0009_bedrock_credentials
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_price_table"
down_revision: str | None = "0009_bedrock_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRICE = sa.Numeric(12, 6)


def upgrade() -> None:
    op.create_table(
        "model_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input", PRICE, nullable=False),
        sa.Column("output", PRICE, nullable=False),
        sa.Column("cached_input", PRICE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_prices"),
        sa.UniqueConstraint("provider", "model", "effective_from", name="uq_model_prices_provider"),
    )
    op.create_table(
        "price_overrides",
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
                name="fk_price_overrides_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            sa.Uuid(),
            sa.ForeignKey(
                "provider_credentials.id",
                ondelete="CASCADE",
                name="fk_price_overrides_credential_id_provider_credentials",
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("input", PRICE, nullable=True),
        sa.Column("output", PRICE, nullable=True),
        sa.Column("cached_input", PRICE, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_price_overrides"),
        sa.UniqueConstraint("credential_id", "model", name="uq_price_overrides_credential_id"),
    )
    op.create_index("ix_price_overrides_organisation_id", "price_overrides", ["organisation_id"])


def downgrade() -> None:
    op.drop_table("price_overrides")
    op.drop_table("model_prices")
