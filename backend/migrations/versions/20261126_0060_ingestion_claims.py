"""Interrupted ingestion restarts (spec 21, ADR-0020): a Document and a staged edition record
when they were last put on Queued, and, while Processing, the claim of the ingestion holding them
and its last heartbeat.

Rows already Queued or Processing take their last update as those times, so the first sweep
deals with Documents stuck before this shipped by the same rules as any other.

Revision ID: 0060_ingestion_claims
Revises: 0059_block_rate_checked_at
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060_ingestion_claims"
down_revision: str | None = "0059_block_rate_checked_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("documents", "staged_editions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("claim_id", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {table} SET queued_at = updated_at WHERE status = 'queued'")  # noqa: S608
        op.execute(f"UPDATE {table} SET heartbeat_at = updated_at WHERE status = 'processing'")  # noqa: S608


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "heartbeat_at")
        op.drop_column(table, "claim_id")
        op.drop_column(table, "queued_at")
