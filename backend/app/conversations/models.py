"""Conversation and Message tables, introduced for the Playground and extended in spec 07, and
the Calls of spec 20.

A Playground Conversation has ``is_playground`` set, so metrics (spec 07) can leave it out.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
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
    # When an Owner deleted it on request: its Messages' text and feedback comments are purged
    # and its Conversation token cleared, while its numbers stay for the metrics.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Call(IdMixin, Base):
    """A Call (spec 20): a Visitor talking to the Agent inside one of their Conversations, through
    the voice layer. Its Spoken Messages name it. It is open until ``ended_at`` is set."""

    __tablename__ = "calls"
    __table_args__ = (
        # Admission counts an IP address's open Calls, and Beat looks for open Calls to end.
        Index("ix_calls_open_ip", "ip", postgresql_where=text("ended_at IS NULL")),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Conversation.id, ondelete="CASCADE"), index=True
    )
    # The Version that was Live when the Call started. Versions only go with their Agent, which
    # takes its Conversations and Calls with it.
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Visitor's IP address when the Call started: the voice layer, not the Visitor, sends
    # its turns, so their rate limit counts against this address. An address holds at most
    # ``app.embed.call_limits.CALLS_PER_IP`` open Calls with one Agent.
    ip: Mapped[str] = mapped_column(String(64))
    # The Agent's Maximum Call length when the Call started: changing it applies to the next
    # Call, so this Call's token, the widget's timer and Beat all keep to this one.
    max_call_minutes: Mapped[int] = mapped_column(Integer)
    # When the turn endpoint last took a turn of the Call, by the platform's clock; None until
    # the first. A Call with no turn for a minute is ended (``app.embed.call_limits``).
    last_turn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when it ends: its minutes, rounded up, and why it ended (a ``CallEnd``).
    minutes: Mapped[int | None] = mapped_column(Integer)
    end_reason: Mapped[str | None] = mapped_column(String(32))
    # Its Voice Cost in US dollars, frozen when it ends: its minutes times the voice credential's
    # per-minute price then (``app.pricing.table.voice_cost``). Null while open, and when no
    # price was set.
    voice_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))


class CallMinutesUsed(Base):
    """An Agent's Call minutes counter for one UTC date: the minutes of its Visitors' Calls that
    ended that day, measured against its Call minutes budget. Playground Calls don't count."""

    __tablename__ = "call_minutes_used"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    minutes: Mapped[int] = mapped_column(Integer)


class Message(IdMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        # The purge looks for Messages not yet purged, oldest first.
        Index(
            "ix_messages_unpurged_created_at",
            "created_at",
            postgresql_where=text("purged_at IS NULL"),
        ),
    )

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
    # True when no Chunk reached the minimum score, so the answer is the fallback text. In
    # Automatic Retrieval Mode no model was asked (its model is then null); in Agentic mode the
    # model searched, found nothing, and its answer was discarded.
    fallback: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # What the Guardrails decided about the answer: a list of
    # {layer, verdict, action, reason, score}.
    guardrail_outcomes: Mapped[list[dict[str, str | float | None]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # How many Knowledge Searches the answer ran (Agentic Retrieval Mode); 0 in Automatic mode.
    # A call the Search limit refused ran no Search and isn't counted.
    search_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # True when the Agent is Agentic but its effective model can't use tools (the Default Model
    # changed since the Draft was saved), so the answer ran as Automatic: the Automatic fallback.
    automatic_fallback: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # When its text (and any feedback comment on it) was purged, by the Retention Window or a
    # Conversation deleted on request (``app.retention``); ``content`` is then empty. Every
    # number and attribution stays.
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A Spoken Message: said in a Call (the Visitor's transcribed words, or the reply the voice
    # layer spoke), rather than typed. ``call_id`` names the Call.
    spoken: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Call.id, ondelete="SET NULL"), index=True
    )


class Search(IdMixin, Base):
    """One Knowledge Search an answer made in Agentic Retrieval Mode (ADR-0015): the reply's
    ``order``-th (from 1), for the ``query`` the model wrote, how long it took, and whether the
    Search limit refused it. The Chunks it found are its Message retrievals. Purging the
    Message's text (``app.retention``) clears the ``query`` too: it can carry the Visitor's
    words."""

    __tablename__ = "searches"
    __table_args__ = (UniqueConstraint("message_id", "order"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Message.id, ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer)
    query: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    limit_refused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class MessageRetrieval(IdMixin, Base):
    """One Chunk retrieval found for an answer: given to the model (with its ``rank``, the
    number in its label) and maybe ``cited``, or left out with an ``excluded_reason``.
    ``position`` orders the Trace: the Chunks given to the model by rank, then the rest as
    retrieval ranked them. In Agentic Retrieval Mode each belongs to the ``search_id`` that
    found it, in the order of the Searches, and its ``rank`` is the number in its Chunk label,
    which continues across the reply. The Chunk and Document IDs have no foreign keys, so the Trace
    outlives a Chunk replaced with its Document's edition. When the Document is deleted, both
    IDs are cleared and ``document_name``, the name when the answer was given, stays as the
    tombstone."""

    __tablename__ = "message_retrievals"
    __table_args__ = (UniqueConstraint("message_id", "position"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Message.id, ondelete="CASCADE"))
    # The Search that found it; None in Automatic mode.
    search_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Search.id, ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None]
    document_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    # None only for retrievals of Documents deleted before names were kept.
    document_name: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    relevance: Mapped[float] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    cited: Mapped[bool] = mapped_column(Boolean)
    excluded_reason: Mapped[str | None] = mapped_column(String(40))
