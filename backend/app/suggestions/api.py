"""Suggestion routes, under an Agent: start a Suggestion run, list the Agent's Suggestions, and read
one with its changes and evidence. Every Member (Editors and Owners) may use them; another
Organisation's Agents are not found.

Starting reads the Agent's Live Version over a range of UTC days, the last 14 by default, and is
refused for an archived Agent or Project, an Agent never Published, or an Organisation with
neither an Evaluation Model nor a Default Model. The run is returned ``queued`` (or, when tasks
run eagerly, already finished) and the Studio polls it until it is ``completed`` or ``failed``.
An archived Agent's Suggestions can still be read.

Reading a Suggestion resolves each piece of evidence to its date and kinds: a reply to its Live
Verdict outcome and the Conversation and Message the Conversations viewer opens it at, never
its text (ADR-0017), saying ``text_purged`` once the Purge has cleared it; an Evaluation Case to
the Run and copied case Run detail opens its result at, saying ``case_deleted`` once the case is
deleted. It also holds the Knowledge Base gaps the run found.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal, Self, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, model_validator

from app.agents.api import NOT_FOUND_RESPONSE, agent_archived, archived, not_found
from app.agents.service import AgentArchivedError, AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.evaluation.api import ClockDep
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.suggestions import service
from app.suggestions.models import (
    EvidenceKind,
    SuggestedChange,
    Suggestion,
    SuggestionOutcome,
    SuggestionStatus,
)
from app.suggestions.tasks import enqueue_suggestion
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}/suggestions",
    tags=["suggestions"],
)

# The range a run reads unless another is chosen: the last 14 UTC days, today included.
DEFAULT_RANGE_DAYS = 14
NEVER_PUBLISHED = (
    "This Agent has never been Published, so it has no Live Version replies to suggest changes "
    "from. Publish it first."
)
NO_EVALUATION_MODEL = (
    "This Organisation has neither an Evaluation Model nor a Default Model. An Owner can choose "
    "one in Settings, Models."
)
RANGE_BACKWARDS = "The range must start on or before the day it ends."

_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {
        "model": ErrorResponse,
        "description": (
            "The Project or Agent is archived, the Agent has never been Published, or the "
            "Organisation has neither an Evaluation Model nor a Default Model."
        ),
    },
    422: {"description": "The range starts after the day it ends."},
}

SettingValue = str | int | float


class SuggestionRunIn(BaseModel):
    # The first and last UTC days the run reads; by default the last 14 days, today included.
    range_start: date | None = None
    range_end: date | None = None

    @model_validator(mode="after")
    def _forwards(self) -> Self:
        if (
            self.range_start is not None
            and self.range_end is not None
            and self.range_start > self.range_end
        ):
            raise ValueError(RANGE_BACKWARDS)
        return self


class SuggestionSummaryOut(BaseModel):
    id: uuid.UUID
    status: SuggestionStatus
    # The UTC days it read, both included.
    range_start: date
    range_end: date
    # The Live Version it was made from.
    base_version_id: uuid.UUID
    base_version_number: int
    # Null until it completes.
    outcome: SuggestionOutcome | None
    # How much evidence the range held (at most 50 pieces are used).
    evidence_total: int
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None


class SuggestedChangeOut(BaseModel):
    id: uuid.UUID
    # A setting path, such as ``behaviour.system_prompt``.
    path: str
    # Its value in the Live Version the Suggestion was made from.
    base_value: SettingValue
    suggested_value: SettingValue
    explanation: str
    # The evidence it cites.
    evidence_ids: list[uuid.UUID]


class EvidenceOut(BaseModel):
    id: uuid.UUID
    # Its id in the run, such as E1.
    label: str
    # Its first kind, and every kind it qualifies as: a reply can be a failed Live Verdict, have a
    # thumbs-down and be in a Conversation rated 1 or 2 at once.
    kind: EvidenceKind
    kinds: list[EvidenceKind]
    # When the reply was given, or the Run that failed the Evaluation Case finished.
    occurred_at: datetime
    # A reply: where the Conversations viewer opens it. Null for an Evaluation Case.
    conversation_id: uuid.UUID | None
    message_id: uuid.UUID | None
    # The reply's Live Verdict outcome; null when it has none.
    live_verdict: Literal["pass", "fail"] | None
    # The Purge has cleared the reply's text.
    text_purged: bool
    # An Evaluation Case: the Run and the case as it copied it, where Run detail opens its
    # result. Null for a reply.
    evaluation_run_id: uuid.UUID | None
    run_case_id: uuid.UUID | None
    # The Evaluation Case has since been deleted: it reads "Case deleted".
    case_deleted: bool


class KnowledgeBaseGapOut(BaseModel):
    id: uuid.UUID
    # A short topic and why, in the run's own words.
    topic: str
    explanation: str
    # The evidence it cites.
    evidence_ids: list[uuid.UUID]


class SuggestionOut(SuggestionSummaryOut):
    # The run's overall explanation; null until it completes.
    explanation: str | None
    # The Evaluation Model (or Default Model) that proposed it.
    model_provider: str
    model_name: str
    changes: list[SuggestedChangeOut]
    # Topics no Chunk covered; never a change.
    gaps: list[KnowledgeBaseGapOut]
    evidence: list[EvidenceOut]


def _summary(suggestion: Suggestion, base_version_number: int) -> SuggestionSummaryOut:
    return SuggestionSummaryOut(
        id=suggestion.id,
        status=SuggestionStatus(suggestion.status),
        range_start=suggestion.range_start,
        range_end=suggestion.range_end,
        base_version_id=suggestion.base_version_id,
        base_version_number=base_version_number,
        outcome=None if suggestion.outcome is None else SuggestionOutcome(suggestion.outcome),
        evidence_total=suggestion.evidence_total,
        error_message=suggestion.error_message,
        created_at=suggestion.created_at,
        finished_at=suggestion.finished_at,
    )


def _change(change: SuggestedChange, evidence_ids: dict[int, uuid.UUID]) -> SuggestedChangeOut:
    return SuggestedChangeOut(
        id=change.id,
        path=change.path,
        base_value=change.base_value,
        suggested_value=change.suggested_value,
        explanation=change.explanation,
        evidence_ids=[evidence_ids[position] for position in change.evidence],
    )


def _evidence(each: service.EvidenceRead) -> EvidenceOut:
    message, run_case = each.message, each.run_case
    return EvidenceOut(
        id=each.evidence.id,
        label=f"E{each.evidence.position}",
        kind=EvidenceKind(each.evidence.kind),
        kinds=[EvidenceKind(kind) for kind in each.evidence.kinds],
        occurred_at=each.occurred_at,
        conversation_id=None if message is None else message.conversation_id,
        message_id=None if message is None else message.id,
        live_verdict=cast(Literal["pass", "fail"] | None, each.live_verdict),
        text_purged=each.text_purged,
        evaluation_run_id=None if run_case is None else run_case.run_id,
        run_case_id=None if run_case is None else run_case.id,
        case_deleted=each.case_deleted,
    )


def _out(read: service.SuggestionRead) -> SuggestionOut:
    suggestion = read.suggestion
    evidence_ids = {each.evidence.position: each.evidence.id for each in read.evidence}
    return SuggestionOut(
        **_summary(suggestion, read.base_version_number).model_dump(),
        explanation=suggestion.explanation,
        model_provider=suggestion.model_provider,
        model_name=suggestion.model_name,
        changes=[_change(change, evidence_ids) for change in read.changes],
        gaps=[
            KnowledgeBaseGapOut(
                id=gap.id,
                topic=gap.topic,
                explanation=gap.explanation,
                evidence_ids=[evidence_ids[position] for position in gap.evidence],
            )
            for gap in read.gaps
        ],
        evidence=[_evidence(each) for each in read.evidence],
    )


async def _read(
    db: Db, scope: Scope, project_id: uuid.UUID, agent_id: uuid.UUID, suggestion_id: uuid.UUID
) -> SuggestionOut:
    try:
        read = await service.get_suggestion(db, scope, project_id, agent_id, suggestion_id)
    except (ProjectNotFoundError, AgentNotFoundError, service.SuggestionNotFoundError):
        raise not_found() from None
    return _out(read)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startSuggestionRun",
    responses=_START_RESPONSES,
)
async def start_suggestion_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: SuggestionRunIn,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> SuggestionOut:
    """Starts a Suggestion run of the Agent's Live Version over the range. Poll the Suggestion
    until it is no longer in progress."""
    now = clock.now()
    range_end = body.range_end or now.date()
    range_start = body.range_start or range_end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if range_start > range_end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, RANGE_BACKWARDS)
    try:
        suggestion_id = await service.start_suggestion(
            db, scope, project_id, agent_id, range_start=range_start, range_end=range_end, now=now
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    except service.NeverPublishedError:
        raise HTTPException(status.HTTP_409_CONFLICT, NEVER_PUBLISHED) from None
    except service.NoEvaluationModelError:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_EVALUATION_MODEL) from None
    await enqueue_suggestion(suggestion_id)
    # When tasks run eagerly the run has moved on in other sessions: read it afresh.
    db.expire_all()
    return await _read(db, scope, project_id, agent_id, suggestion_id)


@router.get("", operation_id="listSuggestions", responses=NOT_FOUND_RESPONSE)
async def list_suggestions(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> list[SuggestionSummaryOut]:
    """The Agent's Suggestions, newest first."""
    try:
        found = await service.list_suggestions(db, scope, project_id, agent_id)
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return [_summary(suggestion, number) for suggestion, number in found]


@router.get("/{suggestion_id}", operation_id="getSuggestion", responses=NOT_FOUND_RESPONSE)
async def get_suggestion(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    scope: Scope,
    db: Db,
) -> SuggestionOut:
    """The Suggestion with its changes and its evidence resolved."""
    return await _read(db, scope, project_id, agent_id, suggestion_id)
