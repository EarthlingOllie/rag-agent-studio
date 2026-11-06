"""Documents and their Chunks. Both carry the Organisation and Project they belong to, so every
query is filtered by an ordinary ``project_id`` (ADR-0001)."""

import enum
import re
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC, Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    literal,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from app.core.db import Base, IdMixin
from app.embeddings.registry import EMBEDDING_MODELS, EmbeddingModel

# Referenced as objects, so the worker (which loads no routers) has these tables registered too.
from app.projects.models import Project
from app.tenancy.models import Organisation

NAME_MAX = 255
MIME_MAX = 255


class DocumentStatus(enum.StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


FINAL_STATUSES = frozenset({DocumentStatus.READY, DocumentStatus.FAILED})


class FailureCategory(enum.StrEnum):
    """Why a Document failed, so an Editor knows whether to fix the file or retry it."""

    # The file isn't what its type says, or has no readable text.
    UNSUPPORTED_CONTENT = "unsupported_content"
    # The converter couldn't convert it, or something else went wrong while processing it.
    CONVERSION = "conversion"
    # The Embedding Model's provider kept failing, after the automatic retries.
    PROVIDER = "provider"
    # The Project already holds as many Documents as its quota allows.
    QUOTA = "quota"


class Document(IdMixin, Base):
    __tablename__ = "documents"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Project.id, ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    mime_type: Mapped[str] = mapped_column(String(MIME_MAX))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 of the uploaded bytes, hex.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    # The original file in the object store.
    object_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.QUEUED)
    error_message: Mapped[str | None] = mapped_column(Text)
    # A ``FailureCategory``, while the Document is Failed.
    error_category: Mapped[str | None] = mapped_column(String(30))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # The converted markdown in the object store, once converted.
    markdown_key: Mapped[str | None] = mapped_column(Text)
    edition: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagedEdition(Base):
    """A newer edition of a Document, uploaded to replace it and being ingested. Its Chunks are
    written under its own edition number, which nothing reads until the swap makes it the
    Document's edition; until then the Document's current Chunks keep serving. At most one per
    Document: a Failed one is overwritten by the next replacement."""

    __tablename__ = "staged_editions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Project.id, ondelete="CASCADE"), index=True
    )
    edition: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    mime_type: Mapped[str] = mapped_column(String(MIME_MAX))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.QUEUED)
    error_message: Mapped[str | None] = mapped_column(Text)
    # A ``FailureCategory``, while the staged edition is Failed.
    error_category: Mapped[str | None] = mapped_column(String(30))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(IdMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "edition", "embedding_model_id", "ordinal", name="uq_chunks_position"
        ),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Project.id, ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    edition: Mapped[int] = mapped_column(Integer)
    # Position in the Document, from 0.
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # The headings above the Chunk, outermost first.
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # Pages the Chunk comes from; empty for formats without pages (Markdown, HTML, DOCX).
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    # The vector's size depends on the Embedding Model, so the column has no fixed dimension.
    embedding: Mapped[list[float]] = mapped_column(Vector())
    embedding_model_id: Mapped[str] = mapped_column(String(100))
    # Full-text search over the Chunk; 'simple' because Knowledge Bases are multilingual.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple'::regconfig, text)", persisted=True)
    )


# pgvector's HNSW indexes ``vector`` up to this many dimensions; larger models index halfvec.
HNSW_VECTOR_MAX_DIMENSIONS = 2000


def model_slug(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model_id.lower())


def model_vector(model: EmbeddingModel) -> ColumnElement[Any]:
    """The Chunk's vector cast to the model's dimension, as its HNSW index expression has it.
    Ordering by distance from this expression (filtered to the model) uses that index."""
    kind: Any = Vector if model.dimension <= HNSW_VECTOR_MAX_DIMENSIONS else HALFVEC
    return cast(Chunk.embedding, kind(model.dimension))


def _hnsw_index(model: EmbeddingModel) -> Index:
    """An HNSW index over one Embedding Model's vectors. Vectors of different models differ in
    size, so each model gets its own partial index on the column cast to its dimension."""
    slug = model_slug(model.id)
    label = f"embedding_{slug}"
    ops = "vector" if model.dimension <= HNSW_VECTOR_MAX_DIMENSIONS else "halfvec"
    return Index(
        f"ix_chunks_embedding_hnsw_{slug}",
        model_vector(model).label(label),
        postgresql_using="hnsw",
        postgresql_ops={label: f"{ops}_cosine_ops"},
        postgresql_where=Chunk.embedding_model_id == literal(model.id),
    )


for _model in EMBEDDING_MODELS.values():
    _hnsw_index(_model)
