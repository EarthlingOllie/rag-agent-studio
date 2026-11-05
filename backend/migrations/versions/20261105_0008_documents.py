"""Documents and Chunks, and each Project's Embedding Model.

Revision ID: 0008_documents
Revises: 0007_provider_credentials
Create Date: 2026-11-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0008_documents"
down_revision: str | None = "0007_provider_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _owner_columns(table: str) -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name=f"fk_{table}_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey(
                "projects.id", ondelete="CASCADE", name=f"fk_{table}_project_id_projects"
            ),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "embedding_model_id",
            sa.String(100),
            nullable=False,
            server_default="multilingual-e5-small",
        ),
    )
    op.alter_column("projects", "embedding_model_id", server_default=None)

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        *_owner_columns("documents"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("markdown_key", sa.Text(), nullable=True),
        sa.Column("edition", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    for column in ("organisation_id", "project_id", "content_hash"):
        op.create_index(f"ix_documents_{column}", "documents", [column])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        *_owner_columns("chunks"),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "documents.id", ondelete="CASCADE", name="fk_chunks_document_id_documents"
            ),
            nullable=False,
        ),
        sa.Column("edition", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("heading_path", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_model_id", sa.String(100), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, text)", persisted=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id", "edition", "embedding_model_id", "ordinal", name="uq_chunks_position"
        ),
    )
    for column in ("organisation_id", "project_id", "document_id"):
        op.create_index(f"ix_chunks_{column}", "chunks", [column])
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")
    # One HNSW index per Embedding Model: vectors of different models differ in size.
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw_multilingual_e5_small ON chunks "
        "USING hnsw ((embedding::vector(384)) vector_cosine_ops) "
        "WHERE embedding_model_id = 'multilingual-e5-small'"
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_column("projects", "embedding_model_id")
