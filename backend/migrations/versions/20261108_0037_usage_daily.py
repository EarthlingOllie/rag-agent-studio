"""Usage rollups: ``usage_daily`` (per Agent Version per UTC day: Conversations, Messages, token
sums and histogram, frozen cost, thumbs, rating sum and count, fallbacks, latency histograms)
and ``usage_rollup_state`` (per Organisation, the last day whose rollup is final).

Revision ID: 0037_usage_daily
Revises: 0036_token_budget
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_usage_daily"
down_revision: str | None = "0036_token_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _references(column: str, table: str) -> sa.Column[object]:
    return sa.Column(
        column,
        sa.Uuid(),
        sa.ForeignKey(f"{table}.id", ondelete="CASCADE", name=f"fk_usage_daily_{column}_{table}"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "usage_daily",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _references("organisation_id", "organisations"),
        _references("agent_id", "agents"),
        _references("agent_version_id", "agent_versions"),
        sa.Column("day", sa.Date(), nullable=False),
        *(
            sa.Column(name, sa.Integer(), nullable=False)
            for name in ("conversations", "messages", "token_replies")
        ),
        sa.Column("tokens", sa.BigInteger(), nullable=False),
        sa.Column("tokens_histogram", postgresql.JSONB(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 9), nullable=False),
        *(
            sa.Column(name, sa.Integer(), nullable=False)
            for name in ("thumbs_up", "thumbs_down", "rating_sum", "rating_count", "fallback_count")
        ),
        sa.Column("first_token_histogram", postgresql.JSONB(), nullable=False),
        sa.Column("latency_histogram", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("agent_version_id", "day", name="uq_usage_daily_agent_version_id"),
    )
    for column in ("organisation_id", "agent_id", "day"):
        op.create_index(f"ix_usage_daily_{column}", "usage_daily", [column])
    op.create_table(
        "usage_rollup_state",
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_usage_rollup_state_organisation_id_organisations",
            ),
            primary_key=True,
        ),
        sa.Column("finalised_through", sa.Date(), nullable=False),
        sa.Column("finalised_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("usage_rollup_state")
    op.drop_table("usage_daily")
