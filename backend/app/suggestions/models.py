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
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent, AgentVersion
from app.conversations.models import Message
from app.core.db import Base, IdMixin
from app.credentials.models import ProviderCredential
from app.evaluation.models import EvaluationRunCase
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
    # A Visitor reply of the Live Version with a thumbs-down.
    THUMBS_DOWN = "thumbs_down"
    # A Visitor reply of the Live Version in a Conversation whose current Conversation Rating is
    # 1 or 2.
    LOW_RATING = "low_rating"
    # An Evaluation Case that failed on the Live Version in the latest finished Evaluation Run
    # with a side running it.
    EVALUATION_CASE = "evaluation_case"


# The order a reply's kinds are listed in.
REPLY_KINDS = (EvidenceKind.LIVE_VERDICT, EvidenceKind.THUMBS_DOWN, EvidenceKind.LOW_RATING)


class Suggestion(IdMixin, Base):
    """One Suggestion run of an Agent, and the Suggestion it made.

    An Agent has at most one Suggestion run in progress: starting one locks the Agent's row and
    checks (with its Evaluation Runs, so the two never overlap), and a partial unique index backs
    that up."""

    __tablename__ = "suggestions"
    __table_args__ = (
        Index(
            "uq_suggestions_in_progress_agent",
            "agent_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'gathering', 'proposing', 'checking')"),
        ),
    )

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
    # The estimated Cost shown before it started, in US dollars: proposing, and checking (None
    # without an Evaluation Set, or when a price it needed is unknown).
    estimated_proposing_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    estimated_checking_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    # What the proposing call cost, frozen at the prices in force when it was made, and when;
    # None until it is made, or when its model's price is unknown. Organisation cost counts it in
    # its Evaluation column; the Evaluation budget never does.
    proposing_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who applied it to the Draft, and when; None until it is applied (and ``applied_by`` once
    # that Member is gone).
    applied_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    """One piece of evidence the Suggestion was made from: a Visitor reply, by the Message it
    points at and never the Message's text (ADR-0017), or an Evaluation Case's result, by the
    case as the Run copied it. A reply that qualifies several ways is one piece with each of its
    kinds."""

    __tablename__ = "suggestion_evidence"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Suggestion.id, ondelete="CASCADE"), index=True
    )
    # Its label in the proposing call is ``E<position>``.
    position: Mapped[int] = mapped_column(Integer)
    # Its first ``EvidenceKind``, and every one it qualifies as, in ``REPLY_KINDS`` order.
    kind: Mapped[str] = mapped_column(String(30))
    kinds: Mapped[list[str]] = mapped_column(JSONB)
    # The reply; None for an Evaluation Case.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Message.id, ondelete="CASCADE"), index=True
    )
    # The Evaluation Case as its Run copied it; None for a reply. Its ``case_id`` is None once
    # the case is deleted, and the evidence reads "Case deleted".
    run_case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(EvaluationRunCase.id, ondelete="CASCADE"), index=True
    )


class KnowledgeBaseGap(IdMixin, Base):
    """A topic the Suggestion run found that failed replies asked about and no Chunk covered, in
    the run's own words, with the evidence behind it. Never a change: nothing applies it."""

    __tablename__ = "suggestion_gaps"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Suggestion.id, ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)
    # The positions of the evidence it cites.
    evidence: Mapped[list[int]] = mapped_column(JSONB)
