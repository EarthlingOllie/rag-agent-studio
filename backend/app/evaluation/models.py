"""Evaluation Cases, Evaluation Runs, their sides, case results and Verdicts, and Live Verdicts.

Everything here belongs to one Agent and goes with it on Permanent deletion (``ON DELETE
CASCADE``). Apart from Live Verdicts, nothing references a Conversation or a Message, and the
Purge never touches these tables (ADR-0016). A Run copies each case's question and expectations
when it starts (``EvaluationRunCase``), and each side's effective AgentConfig and Instructions
(``EvaluationRunSide``), so editing the set or the Draft later never rewrites a past Run.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent, AgentVersion
from app.conversations.models import Message
from app.core.db import Base, IdMixin
from app.credentials.models import ProviderCredential
from app.documents.models import NAME_MAX, Document
from app.projects.models import InstructionsVersion
from app.tenancy.models import Member, Organisation

# As long as a Visitor message may be.
QUESTION_MAX = 4000
REFERENCE_ANSWER_MAX = 4000
PASSAGE_MAX = 1000


class CaseSource(enum.StrEnum):
    # Written by an Editor in the case editor.
    WRITTEN = "written"
    # Added from an Agent Message (ticket 14-06).
    FROM_MESSAGE = "from_message"


class RunStatus(enum.StrEnum):
    # Started; its task hasn't picked it up yet.
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    # Stopped by an Editor; what it answered and spent so far is kept.
    CANCELLED = "cancelled"


# Queued or running: an Agent has at most one such Run.
IN_PROGRESS = (RunStatus.QUEUED, RunStatus.RUNNING)


class RunKind(enum.StrEnum):
    # Started from the Agent: any one or two of the Draft and its Versions.
    AGENT = "agent"
    # Started by Rollout evaluation: the Live Version against its rollout side.
    ROLLOUT = "rollout"
    # Started by a Suggestion run (spec 16): the Live Version against the Suggestion, its check.
    SUGGESTION = "suggestion"


class SideKind(enum.StrEnum):
    DRAFT = "draft"
    VERSION = "version"
    # The Live Version's AgentConfig answering with a new Instructions Version, not the one it
    # pins. Only Rollout evaluation creates one, never the general Run API.
    ROLLOUT = "rollout"
    # The Live Version's AgentConfig with a Suggestion's changes, answering with the Instructions
    # the Live Version pins. Only a Suggestion run's check creates one, never the general Run
    # API; it is never a Version.
    SUGGESTION = "suggestion"


class ResultStatus(enum.StrEnum):
    ANSWERED = "answered"
    # The provider failed or timed out answering, or the Evaluation Model judging.
    ERROR = "error"


class VerdictKind(enum.StrEnum):
    EXPECTED_SOURCE = "expected_source"
    FALLBACK = "fallback"
    REFERENCE_ANSWER = "reference_answer"
    GROUNDING = "grounding"


class StaleReason(enum.StrEnum):
    DOCUMENT_DELETED = "document_deleted"
    # No Chunk of the Document's current Edition holds the passage.
    PASSAGE_MISSING = "passage_missing"


class VerdictOutcome(enum.StrEnum):
    PASS = "pass"  # noqa: S105 (a Verdict outcome, not a password)
    FAIL = "fail"
    # A Stale expectation, skipped: neither pass nor fail.
    STALE = "stale"


class EvaluationModel(IdMixin, Base):
    """The Organisation's Evaluation Model: a chat-capable credential and one of its chat models,
    the shape of the Default Model's row. No row: the Default Model judges.

    The credential is registered as a reference (``app.evaluation.settings``), so it can't be
    deleted while it is chosen; the foreign key backs that up."""

    __tablename__ = "evaluation_models"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), unique=True
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ProviderCredential.id), index=True)
    model: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# The longest Judging guidance (spec 19), in characters.
GUIDANCE_MAX = 2000


class GuidanceSource(enum.StrEnum):
    # Written by an Owner in the guidance editor.
    WRITTEN = "written"
    # Drafted by the Evaluation Model from Editors' disagreements, then saved by an Owner.
    DRAFTED = "drafted"


class JudgingGuidanceVersion(IdMixin, Base):
    """One saved version of an Organisation's Judging guidance (spec 19): its own instructions to
    the Evaluation Model, added to every judgement. Versions are numbered from 1 per
    Organisation and never change; the Organisation points at its current one
    (``Organisation.judging_guidance_version``). Empty text means none: removing guidance saves
    an empty version. Evaluation Runs and Live Verdicts name the version they were judged under
    by its number, beside the Evaluation Model (their Judging setup)."""

    __tablename__ = "judging_guidance_versions"
    __table_args__ = (UniqueConstraint("organisation_id", "version"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(GUIDANCE_MAX))
    # A ``GuidanceSource``.
    source: Mapped[str] = mapped_column(String(20))
    saved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _judged_under(table: str) -> ForeignKeyConstraint:
    """A judgement's guidance version, always its own Organisation's."""
    return ForeignKeyConstraint(
        ["organisation_id", "judging_guidance_version"],
        [JudgingGuidanceVersion.organisation_id, JudgingGuidanceVersion.version],
        name=f"fk_{table}_judging_guidance_version",
    )


class EvaluationCase(IdMixin, Base):
    """One standalone question in an Agent's Evaluation Set, with what a good answer does."""

    __tablename__ = "evaluation_cases"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    # What a good answer says, in the Editor's words; None when the case expects something else.
    reference_answer: Mapped[str | None] = mapped_column(Text)
    # Whether a good answer is the Fallback Text (or the Refusal text). It stands alone: never
    # with a Reference answer or an Expected source.
    expect_fallback: Mapped[bool] = mapped_column(Boolean, server_default=false())
    source: Mapped[str] = mapped_column(String(20), default=CaseSource.WRITTEN)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationExpectedSource(IdMixin, Base):
    """A passage of a Document that a good answer to the case retrieves and cites.

    It references the Document, not a Chunk, because Chunks are replaced with every Edition: the
    passage is matched against the current Edition's Chunks whenever it is checked. Deleting the
    Document leaves the row, its ``document_name`` kept as a tombstone, and the Expected source is
    a Stale expectation."""

    __tablename__ = "evaluation_expected_sources"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationCase.id, ondelete="CASCADE"), index=True
    )
    # Its order in the case.
    position: Mapped[int] = mapped_column(Integer)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Document.id, ondelete="SET NULL"), index=True
    )
    document_name: Mapped[str] = mapped_column(String(NAME_MAX))
    passage: Mapped[str] = mapped_column(Text)
    # Whether it was a Stale expectation when last checked, and why (a ``StaleReason``).
    stale: Mapped[bool] = mapped_column(Boolean, server_default=false())
    stale_reason: Mapped[str | None] = mapped_column(String(30))


class EvaluationRun(IdMixin, Base):
    """One run of an Agent's Evaluation Set. The Studio polls its status and progress.

    An Agent has at most one queued or running Run: starting one locks the Agent's row and
    checks, and a partial unique index backs that up."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        _judged_under("evaluation_runs"),
        Index(
            "uq_evaluation_runs_in_progress_agent",
            "agent_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.QUEUED)
    # A ``RunKind``.
    kind: Mapped[str] = mapped_column(String(20), server_default=RunKind.AGENT.value)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    # The model that judged the Run's answers and the Evaluation repeats, as they were in force
    # when it started (the Evaluation Model, or else the Default Model), so later changes to
    # the Organisation's settings don't rewrite it.
    judge_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ProviderCredential.id, ondelete="SET NULL"), index=True
    )
    judge_provider: Mapped[str] = mapped_column(String(50))
    judge_model: Mapped[str] = mapped_column(String(200))
    repeats: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    # The Judging guidance version in force when it started, beside its judge model (its
    # Judging setup); None when the Organisation had never saved guidance.
    judging_guidance_version: Mapped[int | None] = mapped_column(Integer)
    # Answers done (answered or errored) out of every answer the Run gives.
    answers_done: Mapped[int] = mapped_column(Integer, default=0)
    answers_total: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    # The estimated Cost shown before it started (``app.evaluation.estimate``), in US dollars;
    # None when a price it needed is unknown. Its actual Cost is its case results'.
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationRunSide(IdMixin, Base):
    """One side of a Run: the Draft (at a Draft revision), an Agent Version, a rollout side (an
    Agent Version's AgentConfig with other Instructions), or a suggestion side (an Agent
    Version's AgentConfig with a Suggestion's changes), with the effective AgentConfig and the
    Project Instructions text it answered with."""

    __tablename__ = "evaluation_run_sides"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationRun.id, ondelete="CASCADE"), index=True
    )
    # ``first`` or ``second``; a Draft running alone is the ``first``.
    position: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(20))
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(AgentVersion.id, ondelete="CASCADE"), index=True
    )
    draft_revision: Mapped[int | None] = mapped_column(Integer)
    # The Instructions Version answered with; None with ``instructions_draft`` for the
    # Instructions Draft, or without it when the Project had no Instructions Version.
    instructions_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(InstructionsVersion.id, ondelete="CASCADE"), index=True
    )
    instructions_draft: Mapped[bool] = mapped_column(Boolean, server_default=false())
    instructions: Mapped[str] = mapped_column(Text)
    # The effective AgentConfig, as JSON (its Automatic fallback applied).
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    chat_provider: Mapped[str] = mapped_column(String(50))
    chat_model: Mapped[str] = mapped_column(String(200))
    automatic_fallback: Mapped[bool] = mapped_column(Boolean, server_default=false())


class EvaluationRunCase(IdMixin, Base):
    """A case as the Run copied it when it started."""

    __tablename__ = "evaluation_run_cases"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationRun.id, ondelete="CASCADE"), index=True
    )
    # The case it was copied from, forgotten once the case is deleted.
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(EvaluationCase.id, ondelete="SET NULL"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    expect_fallback: Mapped[bool] = mapped_column(Boolean, server_default=false())
    # Each Expected source as copied: ``source_id``, ``document_id``, ``document_name`` and
    # ``passage``.
    expected_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )


class EvaluationCaseResult(IdMixin, Base):
    """One answer of one side to one case, with its Trace, or the error that stopped it."""

    __tablename__ = "evaluation_case_results"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationRun.id, ondelete="CASCADE"), index=True
    )
    side_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationRunSide.id, ondelete="CASCADE"), index=True
    )
    run_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationRunCase.id, ondelete="CASCADE"), index=True
    )
    repeat: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20))
    error_reason: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    # The answer's Trace as the Studio reads it (``app.playground.api.TraceOut``), Chunk text
    # included as it was when the Run answered.
    trace: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # What the answer and judging it cost, each frozen with the prices in force when it ran;
    # None when nothing was spent on it or a price was unknown.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    judge_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))


class EvaluationVerdict(IdMixin, Base):
    """A case result's pass or fail on one expectation, or on grounding, with the judge's
    reason."""

    __tablename__ = "evaluation_verdicts"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationCaseResult.id, ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    # Its order among the result's Verdicts: Expected sources (in the case's order), Expect
    # Fallback Text, the Reference answer, then grounding.
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    outcome: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(Text)


class LiveStatus(enum.StrEnum):
    # Chosen; its judging task hasn't finished.
    PENDING = "pending"
    JUDGED = "judged"
    # The Evaluation Model failed or timed out; left out of the Live score.
    ERROR = "error"
    # Its text was Purged before it was judged.
    SKIPPED = "skipped"


class LiveVerdict(IdMixin, Base):
    """The judgement of one Visitor reply chosen by the Live sample rate (spec 15): whether it is
    grounded and answers the question, each pass or fail with a reason, and the overall pass.
    One per Agent Message. The Agent and Agent Version are copied from the Message's attribution;
    the Evaluation Model, Cost and token usage are frozen when it is judged. Unlike Evaluation
    Cases, Live Verdicts aren't an exception to retention: the Purge of its Message clears its
    reasons."""

    __tablename__ = "live_verdicts"
    __table_args__ = (_judged_under("live_verdicts"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Message.id, ondelete="CASCADE"), unique=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(AgentVersion.id, ondelete="CASCADE"), index=True
    )
    # A ``LiveStatus``.
    status: Mapped[str] = mapped_column(String(20), default=LiveStatus.PENDING)
    # Each check's ``VerdictOutcome`` (pass or fail) and reason; None until judged.
    grounded: Mapped[str | None] = mapped_column(String(10))
    grounded_reason: Mapped[str | None] = mapped_column(Text)
    answers_question: Mapped[str | None] = mapped_column(String(10))
    answers_question_reason: Mapped[str | None] = mapped_column(Text)
    # Both checks passed; None until judged.
    passed: Mapped[bool | None] = mapped_column(Boolean)
    error_reason: Mapped[str | None] = mapped_column(Text)
    # The Evaluation Model that judged it (or the Default Model, when none is chosen).
    judge_provider: Mapped[str | None] = mapped_column(String(50))
    judge_model: Mapped[str | None] = mapped_column(String(200))
    # The Judging guidance version in force when judging started, beside the judge model (its
    # Judging setup); None before then, or when the Organisation had never saved guidance.
    judging_guidance_version: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # US dollars, frozen with the prices in force when judged; None when a price is unknown.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    judged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the Purge cleared its reasons, with its Message's text (``app.retention``): they can
    # quote the Visitor. Its outcomes, Cost and counts stay.
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationSpend(IdMixin, Base):
    """What an Organisation's Live Verdicts have spent in one calendar month (UTC), against its
    Evaluation budget, and when its Owners were emailed that the budget was spent. A new month
    is a new row, so the budget resets without a job (``app.evaluation.budget``)."""

    __tablename__ = "evaluation_spend"
    __table_args__ = (UniqueConstraint("organisation_id", "month"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE")
    )
    # The first day of the month.
    month: Mapped[date] = mapped_column(Date)
    # US dollars, the sum of the month's Live Verdicts' frozen Costs.
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), server_default=text("0"))
    # Set by the judgement that took the spend to or past the budget, which emailed the Owners.
    budget_spent_emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
