"""The Message Feedback table (at most one per Agent Message) and the Conversation Rating
tables (the current rating per Conversation, and its append-only change log).

The Agent Version is copied from the Message when the feedback is written, so the feedback stays
with the Version that gave the reply whatever is Live later (a revert moves nothing)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.conversations.models import Conversation, Message
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


SCORE_MIN = 1
SCORE_MAX = 5


class ConversationRating(IdMixin, Base):
    """A Visitor Conversation's current Conversation Rating, and whether the Visitor dismissed
    the rating prompt: at most one per Conversation. The row exists once either happened, so
    ``score`` is None when the prompt was only dismissed.

    The Agent Version is that of the last Agent reply before the rating (or its latest change),
    stored when written."""

    __tablename__ = "conversation_ratings"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Conversation.id, ondelete="CASCADE"), unique=True
    )
    score: Mapped[int | None] = mapped_column(SmallInteger, index=True)
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id"), index=True
    )
    # When the Visitor rated, or last changed the rating.
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the Visitor last dismissed the rating prompt; None when they never did.
    prompt_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"score BETWEEN {SCORE_MIN} AND {SCORE_MAX}", name="score_from_1_to_5"),
    )


class ConversationRatingChange(IdMixin, Base):
    """The append-only change log of Conversation Ratings: one row for the first rating and for
    each change, with the score before it and the Agent Version it was attributed to."""

    __tablename__ = "conversation_rating_changes"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Conversation.id, ondelete="CASCADE"), index=True
    )
    # Orders the log, even when two changes share a timestamp.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    score: Mapped[int] = mapped_column(SmallInteger)
    # None for the first rating.
    previous_score: Mapped[int | None] = mapped_column(SmallInteger)
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id"), index=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
