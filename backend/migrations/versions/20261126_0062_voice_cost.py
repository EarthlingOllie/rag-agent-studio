"""Voice Cost (spec 20): the platform's per-minute voice prices, a voice credential's per-minute
Price override, each Call's frozen Voice Cost, and Voice Cost in the daily rollups.

Revision ID: 0062_voice_cost
Revises: 0061_call_limits
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_voice_cost"
down_revision: str | None = "0061_call_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PER_MINUTE = sa.Numeric(12, 6)


def upgrade() -> None:
    op.create_table(
        "voice_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("per_minute", PER_MINUTE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_voice_prices"),
        sa.UniqueConstraint("provider", "effective_from", name="uq_voice_prices_provider"),
    )
    op.create_table(
        "voice_price_overrides",
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
                name="fk_voice_price_overrides_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            sa.Uuid(),
            sa.ForeignKey(
                "provider_credentials.id",
                ondelete="CASCADE",
                name="fk_voice_price_overrides_credential_id_provider_credentials",
            ),
            nullable=False,
        ),
        sa.Column("per_minute", PER_MINUTE, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_voice_price_overrides"),
        sa.UniqueConstraint("credential_id", name="uq_voice_price_overrides_credential_id"),
    )
    op.create_index(
        "ix_voice_price_overrides_organisation_id", "voice_price_overrides", ["organisation_id"]
    )
    op.add_column("calls", sa.Column("voice_cost_usd", sa.Numeric(18, 9), nullable=True))
    op.add_column(
        "usage_daily",
        sa.Column("voice_cost_usd", sa.Numeric(18, 9), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("usage_daily", "voice_cost_usd")
    op.drop_column("calls", "voice_cost_usd")
    op.drop_index("ix_voice_price_overrides_organisation_id", table_name="voice_price_overrides")
    op.drop_table("voice_price_overrides")
    op.drop_table("voice_prices")
