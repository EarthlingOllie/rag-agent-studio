"""The Project table. Every Project belongs to one Organisation; nothing crosses a Project."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin
from app.embeddings.registry import DEFAULT_MODEL_ID

NAME_MAX = 200
DESCRIPTION_MAX = 2000
# The same limit as an Agent's system prompt.
INSTRUCTIONS_MAX = 20_000
# The note an Editor publishes a Version with.
NOTE_MAX = 500

# How many Documents (not counting Failed ones) a new Project may hold; an Owner can change it.
DEFAULT_DOCUMENT_QUOTA = 500


class FlaggedChunkMode(enum.StrEnum):
    """What retrieval does with the Chunks the ingestion Guardrail scan flags."""

    # They are retrieved as usual, and marked in the Document viewer.
    MARK = "mark"
    # They are never retrieval candidates; the Trace lists them as left out by the scan.
    EXCLUDE = "exclude"


class Project(IdMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("flagged_chunk_mode IN ('mark', 'exclude')", name="flagged_chunk_mode"),
    )

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
    # The Flagged Chunk mode: whether Chunks the ingestion Guardrail scan flags are only marked,
    # or excluded from retrieval. Marked by default, so a false positive doesn't silently hide
    # content; an Editor chooses to quarantine.
    flagged_chunk_mode: Mapped[str] = mapped_column(
        String(10), default=FlaggedChunkMode.MARK, server_default=FlaggedChunkMode.MARK
    )
    # The Provider Credential a provider Embedding Model is called through; None for the local
    # model. Registered as a reference, so the credential can't be deleted while it is in use;
    # the foreign key backs that up.
    embedding_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_credentials.id"), index=True
    )
    # The Project Instructions Draft: the one editable markdown, stored exactly as written.
    # Publishing it makes a new ``InstructionsVersion``.
    instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    # 1, 2, 3…: moves on whenever the Draft's text changes. A save may name the revision it was
    # made on, and is refused when the Draft has moved on since (optimistic concurrency).
    instructions_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # The Current Version: the Instructions Version new Agent Versions pin by default. None
    # until the Instructions are first published.
    current_instructions_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "project_instructions_versions.id",
            name="fk_projects_current_instructions_version",
            use_alter=True,
        )
    )


class InstructionsVersion(IdMixin, Base):
    """An immutable, numbered snapshot of a Project's Instructions Draft. Migration
    ``0025_instructions_versions`` adds a trigger that refuses every UPDATE; rows go only with
    their Project."""

    __tablename__ = "project_instructions_versions"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Project.id, ondelete="CASCADE"))
    # 1, 2, 3… per Project, allocated under the Project's row lock.
    number: Mapped[int] = mapped_column(Integer)
    markdown: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    # Who published it; None for the v1 the migration made from the Instructions already there.
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("members.id"))
    # The Current Version when this one was published. Reverting while this Version is Current
    # goes back to it.
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "project_instructions_versions.id", name="fk_project_instructions_versions_previous"
        )
    )
