"""The Message Feedback table: at most one per Agent Message.

The Agent Version is copied from the Message when the feedback is written, so the feedback stays
with the Version that gave the reply whatever is Live later (a revert moves nothing)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.conversations.models import Message
from app.core.db import Base, IdMixin

COMMENT_MAX = 1000


class Thumb(enum.StrEnum):
    UP = "up"
    DOWN = "down"


class MessageFeedback(IdMixin, Base):
    __tablename__ = "message_feedback"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Message.id, ondelete="CASCADE"), unique=True
    )
    # The Message's Agent Version, stored when written; None only for a Draft answer, which
    # Visitors never see.
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id"), index=True
    )
    rating: Mapped[str] = mapped_column(String(10))
    comment: Mapped[str | None] = mapped_column(Text)
    # When the Visitor last gave or changed it.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
