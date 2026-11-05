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
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


# Which configuration answered: the Draft (Playground); spec 05 adds Version references.
DRAFT = "draft"


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
    model_provider: Mapped[str | None] = mapped_column(String(40))
    model_name: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # Milliseconds from the question to the first token, and to the whole answer.
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # US dollars, from ``app.pricing.table.cost``; None when no price is known.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
