"""Staged editions: a newer edition of a Document, ingested while the current one serves.

Revision ID: 0014_staged_editions
Revises: 0013_tags
Create Date: 2026-11-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0014_staged_editions"
down_revision: str | None = "0013_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "staged_editions",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "documents.id", ondelete="CASCADE", name="fk_staged_editions_document_id_documents"
            ),
            primary_key=True,
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_staged_editions_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey(
                "projects.id", ondelete="CASCADE", name="fk_staged_editions_project_id_projects"
            ),
            nullable=False,
        ),
        sa.Column("edition", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    for column in ("organisation_id", "project_id", "content_hash"):
        op.create_index(f"ix_staged_editions_{column}", "staged_editions", [column])


def downgrade() -> None:
    op.drop_table("staged_editions")
