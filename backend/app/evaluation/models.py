"""Evaluation Cases, Evaluation Runs, their sides, case results and Verdicts.

Everything here belongs to one Agent and goes with it on Permanent deletion (``ON DELETE
CASCADE``). Nothing references a Conversation or a Message, and the Purge never touches these
tables (ADR-0016). A Run copies each case's question and expectations when it starts
(``EvaluationRunCase``), and each side's effective AgentConfig and Instructions
(``EvaluationRunSide``), so editing the set or the Draft later never rewrites a past Run.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent, AgentVersion
from app.core.db import Base, IdMixin
from app.credentials.models import ProviderCredential
from app.projects.models import InstructionsVersion
from app.tenancy.models import Member, Organisation

# As long as a Visitor message may be.
QUESTION_MAX = 4000
REFERENCE_ANSWER_MAX = 4000


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


class SideKind(enum.StrEnum):
    DRAFT = "draft"
    VERSION = "version"


class ResultStatus(enum.StrEnum):
    ANSWERED = "answered"
    # The provider failed or timed out answering, or the Evaluation Model judging.
    ERROR = "error"


class VerdictKind(enum.StrEnum):
    REFERENCE_ANSWER = "reference_answer"
    GROUNDING = "grounding"


class VerdictOutcome(enum.StrEnum):
    PASS = "pass"  # noqa: S105 (a Verdict outcome, not a password)
    FAIL = "fail"


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
    source: Mapped[str] = mapped_column(String(20), default=CaseSource.WRITTEN)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationRun(IdMixin, Base):
    """One run of an Agent's Evaluation Set. The Studio polls its status and progress."""

    __tablename__ = "evaluation_runs"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.QUEUED)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Member.id, ondelete="SET NULL"))
    # The model that judges the Run's answers when it started: the Default Model, for now.
    judge_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ProviderCredential.id, ondelete="SET NULL"), index=True
    )
    judge_provider: Mapped[str] = mapped_column(String(50))
    judge_model: Mapped[str] = mapped_column(String(200))
    # Answers done (answered or errored) out of every answer the Run gives.
    answers_done: Mapped[int] = mapped_column(Integer, default=0)
    answers_total: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationRunSide(IdMixin, Base):
    """One side of a Run: the Draft (at a Draft revision) or an Agent Version, with the
    effective AgentConfig and the Project Instructions text it answered with."""

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
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))


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
    outcome: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(Text)
