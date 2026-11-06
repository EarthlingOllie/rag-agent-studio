"""Re-embed jobs. A Project has at most one running job: its pending Embedding Model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin
from app.credentials.models import ProviderCredential
from app.projects.models import Project
from app.tenancy.models import Member, Organisation


class ReEmbedStatus(enum.StrEnum):
    # Writing the pending model's vectors; the active model keeps serving.
    RUNNING = "running"
    # Switched: the pending model became the active one and the old vectors were deleted.
    COMPLETED = "completed"
    # Stopped by an error; the active model is unchanged and the new vectors were deleted.
    FAILED = "failed"
    # Replaced by another choice before it finished; its vectors were deleted.
    CANCELLED = "cancelled"


class ReEmbedJob(IdMixin, Base):
    """One re-embed of a Project's Knowledge Base, from its active Embedding Model to a pending
    one. Kept after it ends, so the Studio can show how the last one went."""

    __tablename__ = "re_embed_jobs"
    __table_args__ = (
        Index(
            "uq_re_embed_jobs_running_project",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Project.id, ondelete="CASCADE"), index=True
    )
    # The Project's active Embedding Model when the job started, whose Chunks it re-embeds.
    from_model_id: Mapped[str] = mapped_column(String(100))
    # The pending Embedding Model, and the Provider Credential it is called through (none for
    # the local model). A running job's credential is a reference, so it can't be deleted;
    # a finished job's is forgotten if the credential is deleted later.
    model_id: Mapped[str] = mapped_column(String(100))
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ProviderCredential.id, ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=ReEmbedStatus.RUNNING)
    # Progress once the job has ended; while it runs, progress is counted from the Chunks.
    embedded_chunks: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    # Why a failed job failed, readable by an Editor.
    error_message: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
