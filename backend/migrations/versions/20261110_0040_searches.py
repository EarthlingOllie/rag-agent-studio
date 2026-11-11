"""Agentic retrieval: a Search per Knowledge Search an answer made (``searches``: its order,
query, latency and whether the Search limit refused it), the Search each Message retrieval was
found by (``message_retrievals.search_id``, null in Automatic mode) and each Message's
``search_count``.

Revision ID: 0040_searches
Revises: 0039_retention_tombstones
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_searches"
down_revision: str | None = "0039_retention_tombstones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "searches",
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
                name="fk_searches_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey(
                "messages.id", ondelete="CASCADE", name="fk_searches_message_id_messages"
            ),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("limit_refused", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.UniqueConstraint("message_id", "order", name="uq_searches_message_id"),
    )
    op.create_index("ix_searches_organisation_id", "searches", ["organisation_id"])
    op.add_column(
        "message_retrievals",
        sa.Column(
            "search_id",
            sa.Uuid(),
            sa.ForeignKey(
                "searches.id", ondelete="CASCADE", name="fk_message_retrievals_search_id_searches"
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_message_retrievals_search_id", "message_retrievals", ["search_id"])
    op.add_column(
        "messages",
        sa.Column("search_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("messages", "search_count")
    op.drop_index("ix_message_retrievals_search_id", table_name="message_retrievals")
    op.drop_column("message_retrievals", "search_id")
    op.drop_index("ix_searches_organisation_id", table_name="searches")
    op.drop_table("searches")
