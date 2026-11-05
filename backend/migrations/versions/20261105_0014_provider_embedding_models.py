"""Provider Embedding Models: a Project's embedding credential, and an HNSW index per model.

Revision ID: 0014_provider_embedding_models
Revises: 0013_tags
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_provider_embedding_models"
down_revision: str | None = "0013_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index slug, model ID, column type). HNSW indexes ``vector`` up to 2,000 dimensions, so the
# 3,072-dimension model is indexed as halfvec.
_MODELS = (
    ("text_embedding_3_small", "text-embedding-3-small", "vector(1536)"),
    ("text_embedding_3_large", "text-embedding-3-large", "halfvec(3072)"),
    ("voyage_3_5", "voyage-3.5", "vector(1024)"),
    ("voyage_3_5_lite", "voyage-3.5-lite", "vector(1024)"),
    ("voyage_multilingual_2", "voyage-multilingual-2", "vector(1024)"),
    ("amazon_titan_embed_text_v2_0", "amazon.titan-embed-text-v2:0", "vector(1024)"),
    ("cohere_embed_multilingual_v3", "cohere.embed-multilingual-v3", "vector(1024)"),
)


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "embedding_credential_id",
            sa.Uuid(),
            sa.ForeignKey(
                "provider_credentials.id",
                name="fk_projects_embedding_credential_id_provider_credentials",
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_projects_embedding_credential_id", "projects", ["embedding_credential_id"])
    for slug, model_id, column_type in _MODELS:
        ops = column_type.split("(")[0]
        op.execute(
            f"CREATE INDEX ix_chunks_embedding_hnsw_{slug} ON chunks "
            f"USING hnsw ((embedding::{column_type}) {ops}_cosine_ops) "
            f"WHERE embedding_model_id = '{model_id}'"
        )


def downgrade() -> None:
    for slug, _, _ in _MODELS:
        op.drop_index(f"ix_chunks_embedding_hnsw_{slug}", table_name="chunks")
    op.drop_index("ix_projects_embedding_credential_id", table_name="projects")
    op.drop_column("projects", "embedding_credential_id")
