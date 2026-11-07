"""Conversation and Message tables, introduced for the Playground and extended in spec 07.

A Playground Conversation has ``is_playground`` set, so metrics (spec 07) can leave it out.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


# Which configuration answered: the Draft (Playground), or an Agent Version, which the Message
# then names in ``agent_version_id``.
DRAFT = "draft"
VERSION = "version"


class InstructionsSource(enum.StrEnum):
    """Which Project Instructions an answer ran with: the Instructions Draft (the Playground's
    default) or a chosen Instructions Version (named by ``instructions_version_id``)."""

    DRAFT = "draft"
    VERSION = "version"


class Conversation(IdMixin, Base):
    __tablename__ = "conversations"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    is_playground: Mapped[bool] = mapped_column(Boolean)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # A Visitor Conversation's Conversation token, as its SHA-256 hex digest; the token itself is
    # only ever held by the Visitor's widget. None for Playground Conversations.
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)


class Message(IdMixin, Base):
    __tablename__ = "messages"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Conversation.id, ondelete="CASCADE"), index=True
    )
    # Orders a Conversation's Messages, even when two share a timestamp.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    # Set on assistant Messages only.
    config_source: Mapped[str | None] = mapped_column(String(40))
    # The Project Instructions the answer ran with: an ``InstructionsSource``, and the Version
    # when it was one. Versions only go with their Project, which takes its Messages with it.
    instructions_source: Mapped[str | None] = mapped_column(String(20))
    instructions_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "project_instructions_versions.id",
            name="fk_messages_instructions_version",
            ondelete="CASCADE",
        )
    )
    # The Agent Version that answered; None for a Draft answer (and for questions).
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_versions.id"))
    model_provider: Mapped[str | None] = mapped_column(String(40))
    model_name: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # Milliseconds from the question to the first token, and to the whole answer.
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # US dollars, from ``app.pricing.table.cost``; None when no price is known.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    # True when no Chunk reached the minimum score, so the answer is the fallback text and no
    # model was asked (its model is then null).
    fallback: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # What the Guardrails decided about the answer: a list of {layer, verdict, action, reason}.
    guardrail_outcomes: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )


class MessageRetrieval(IdMixin, Base):
    """One Chunk retrieval found for an answer: given to the model (with its ``rank``, the
    number in its label) and maybe ``cited``, or left out with an ``excluded_reason``.
    ``position`` orders the Trace: the Chunks given to the model by rank, then the rest as
    retrieval ranked them. The Chunk and Document IDs have no foreign keys, so the Trace
    outlives a Chunk replaced or deleted with its Document."""

    __tablename__ = "message_retrievals"
    __table_args__ = (UniqueConstraint("message_id", "position"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Message.id, ondelete="CASCADE"))
    chunk_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    position: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    relevance: Mapped[float] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    cited: Mapped[bool] = mapped_column(Boolean)
    excluded_reason: Mapped[str | None] = mapped_column(String(40))
