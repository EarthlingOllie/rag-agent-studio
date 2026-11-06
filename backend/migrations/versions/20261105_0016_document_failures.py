"""Ingestion failure categories, and each Project's Document quota.

Revision ID: 0016_document_failures
Revises: 0015_provider_embedding_models
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_document_failures"
down_revision: str | None = "0015_provider_embedding_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("error_category", sa.String(30), nullable=True))
    op.add_column("staged_editions", sa.Column("error_category", sa.String(30), nullable=True))
    op.add_column(
        "projects",
        sa.Column("document_quota", sa.Integer(), server_default="500", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("projects", "document_quota")
    op.drop_column("staged_editions", "error_category")
    op.drop_column("documents", "error_category")
