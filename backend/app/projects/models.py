"""The Project table. Every Project belongs to one Organisation; nothing crosses a Project."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin
from app.embeddings.registry import DEFAULT_MODEL_ID

NAME_MAX = 200
DESCRIPTION_MAX = 2000
# How many Documents (not counting Failed ones) a new Project may hold; an Owner can change it.
DEFAULT_DOCUMENT_QUOTA = 500


class Project(IdMixin, Base):
    __tablename__ = "projects"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    description: Mapped[str] = mapped_column(Text, default="")
    # Set while the Project is archived: hidden from the main list, and it stops serving.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Embedding Model the Project's Chunks are embedded with; the local model by default.
    embedding_model_id: Mapped[str] = mapped_column(String(100), default=DEFAULT_MODEL_ID)
    # The most Documents, not counting Failed ones, the Project may hold.
    document_quota: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_DOCUMENT_QUOTA, server_default=str(DEFAULT_DOCUMENT_QUOTA)
    )
    # Whether ingestion runs OCR, so scanned PDFs become readable. Off by default: OCR is slow,
    # and most Projects' files carry their own text.
    ocr_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # The Provider Credential a provider Embedding Model is called through; None for the local
    # model. Registered as a reference, so the credential can't be deleted while it is in use;
    # the foreign key backs that up.
    embedding_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_credentials.id"), index=True
    )
