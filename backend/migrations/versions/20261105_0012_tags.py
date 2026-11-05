"""Tags, scoped to a Project, and the Tags applied to Documents.

Revision ID: 0012_tags
Revises: 0011_documents
Create Date: 2026-11-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0012_tags"
down_revision: str | None = "0011_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _organisation_id(table: str) -> sa.Column[Any]:
    return sa.Column(
        "organisation_id",
        sa.Uuid(),
        sa.ForeignKey(
            "organisations.id",
            ondelete="CASCADE",
            name=f"fk_{table}_organisation_id_organisations",
        ),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _organisation_id("tags"),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_tags_project_id_projects"),
            nullable=False,
        ),
        sa.Column("name", sa.String(50), nullable=False),
    )
    op.create_index("ix_tags_organisation_id", "tags", ["organisation_id"])
    op.create_index("ix_tags_project_id", "tags", ["project_id"])
    op.create_index(
        "uq_tags_project_name", "tags", ["project_id", sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "document_tags",
        _organisation_id("document_tags"),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "documents.id", ondelete="CASCADE", name="fk_document_tags_document_id_documents"
            ),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tags.id", ondelete="CASCADE", name="fk_document_tags_tag_id_tags"),
            primary_key=True,
        ),
    )
    op.create_index("ix_document_tags_organisation_id", "document_tags", ["organisation_id"])
    op.create_index("ix_document_tags_tag_id", "document_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_table("document_tags")
    op.drop_table("tags")
