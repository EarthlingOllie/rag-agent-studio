"""Suggestions (spec 16): an Agent's Suggestion runs and the Suggestions they make, each with its
suggested changes and the evidence behind them.

Everything here belongs to one Agent and goes with it on Permanent deletion (``ON DELETE
CASCADE``). A Suggestion keeps the Live Version it was made from and a snapshot of that Version's
AgentConfig, so a later Publish never rewrites it. Its evidence points at Messages and never
copies their text (ADR-0017): once the Purge clears a Message, the evidence still reads, its text
purged, while the change and its explanation are kept.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent, AgentVersion
from app.conversations.models import Message
from app.core.db import Base, IdMixin
from app.credentials.models import ProviderCredential
from app.tenancy.models import Member, Organisation


class SuggestionStatus(enum.StrEnum):
    # Started; its task hasn't picked it up yet.
    QUEUED = "queued"
    GATHERING = "gathering"
    PROPOSING = "proposing"
    CHECKING = "checking"
    COMPLETED = "completed"
    # The Evaluation Model failed, timed out or gave invalid output.
    FAILED = "failed"
    CANCELLED = "cancelled"


# Not yet finished: the Studio polls a Suggestion in one of these.
IN_PROGRESS = (
    SuggestionStatus.QUEUED,
    SuggestionStatus.GATHERING,
    SuggestionStatus.PROPOSING,
    SuggestionStatus.CHECKING,
)


class SuggestionOutcome(enum.StrEnum):
    CHANGES = "changes"
    # Knowledge Base gaps but no configuration change.
    GAPS_ONLY = "gaps_only"
    NO_CHANGE = "no_change"


class EvidenceKind(enum.StrEnum):
    # A Visitor reply of the Live Version that failed its Live Verdict.
    LIVE_VERDICT = "live_verdict"


class Suggestion(IdMixin, Base):
    """One Suggestion run of an Agent, and the Suggestion it made."""

    __tablename__ = "suggestions"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    # A ``SuggestionStatus``.
    status: Mapped[str] = mapped_column(String(20), default=SuggestionStatus.QUEUED)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    # The range of UTC days it reads, both included.
    range_start: Mapped[date] = mapped_column(Date)
    range_end: Mapped[date] = mapped_column(Date)
    # The Live Version when it started, and a snapshot of its AgentConfig, as JSON.
    base_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(AgentVersion.id, ondelete="CASCADE"), index=True
    )
    base_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The Evaluation Model (or else the Default Model) as it was when it started.
    model_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ProviderCredential.id, ondelete="SET NULL"), index=True
    )
    model_provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(200))
    # How much evidence the range held before the cap, and how much was used.
    evidence_total: Mapped[int] = mapped_column(Integer, default=0)
    # A ``SuggestionOutcome``; None until it completes.
    outcome: Mapped[str | None] = mapped_column(String(20))
    # The run's overall explanation, in its own words.
    explanation: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SuggestedChange(IdMixin, Base):
    """One setting the Suggestion changes: its path, its value in the base configuration, the
    suggested value, and why."""

    __tablename__ = "suggested_changes"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Suggestion.id, ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    # A setting path, such as ``behaviour.system_prompt``.
    path: Mapped[str] = mapped_column(String(100))
    base_value: Mapped[Any] = mapped_column(JSONB)
    suggested_value: Mapped[Any] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    # The positions of the evidence it cites.
    evidence: Mapped[list[int]] = mapped_column(JSONB)


class SuggestionEvidence(IdMixin, Base):
    """One piece of evidence the Suggestion was made from: its kind and the Message it points at,
    never the Message's text (ADR-0017)."""

    __tablename__ = "suggestion_evidence"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Suggestion.id, ondelete="CASCADE"), index=True
    )
    # Its label in the proposing call is ``E<position>``.
    position: Mapped[int] = mapped_column(Integer)
    # An ``EvidenceKind``.
    kind: Mapped[str] = mapped_column(String(30))
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Message.id, ondelete="CASCADE"), index=True
    )
