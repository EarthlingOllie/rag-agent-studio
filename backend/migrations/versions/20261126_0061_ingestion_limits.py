"""Ingestion limits (spec 21, ticket 21-04): a Document and a staged edition count how many times
their ingestion was cut short, apart from the automatic retries, and record when an automatic
retry is due, so the sweeper sends a retry whose message was lost.

Revision ID: 0061_ingestion_limits
Revises: 0060_ingestion_claims
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_ingestion_limits"
down_revision: str | None = "0060_ingestion_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("documents", "staged_editions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("interruption_count", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(table, sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "retry_at")
        op.drop_column(table, "interruption_count")
