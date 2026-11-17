"""Suggestion routes, under an Agent: the run dialog's evidence count and estimate, start and
cancel a Suggestion run, list the Agent's Suggestions, and read one with its changes and
evidence. Every Member (Editors and Owners) may use them; another Organisation's Agents are not
found.

Starting reads the Agent's Live Version over a range of UTC days, the last 14 by default, and is
refused for an archived Agent or Project, an Agent never Published, or an Organisation with
neither an Evaluation Model nor a Default Model; and, with a typed conflict, while the Agent has
a Suggestion run or an Evaluation Run in progress. The dialog's reads are refused alike, except
while a run is in progress. The run is returned ``queued`` (or, when tasks run eagerly, already
finished) with its estimated Cost, and the Studio polls it through ``gathering``, ``proposing``
and ``checking`` until it is ``completed``, ``failed`` or ``cancelled``. An archived Agent's
Suggestions can still be read, and a run in progress cancelled.

Reading a Suggestion resolves each piece of evidence to its date and kinds: a reply to its Live
Verdict outcome and the Conversation and Message the Conversations viewer opens it at, never
its text (ADR-0017), saying ``text_purged`` once the Purge has cleared it; an Evaluation Case to
the Run and copied case Run detail opens its result at, saying ``case_deleted`` once the case is
deleted. It also holds the Knowledge Base gaps the run found.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, Self, cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator

from app.agents.api import NOT_FOUND_RESPONSE, agent_archived, archived, not_found
from app.agents.service import AgentArchivedError, AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.evaluation.api import ClockDep, RunConflict, RunConflictOut, run_conflict
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
SUGGESTION_IN_PROGRESS = (
    "This Agent already has a Suggestion run in progress. Wait for it to finish, or cancel it."
)
EVALUATION_RUN_IN_PROGRESS = (
    "This Agent has an Evaluation Run in progress. Wait for it to finish, or cancel it, then "
    "suggest changes."
)
SUGGESTION_FINISHED = "This Suggestion run has already finished."

_REFUSED = (
    "The Project or Agent is archived, the Agent has never been Published, or the Organisation "
    "has neither an Evaluation Model nor a Default Model."
)
_RANGE_RESPONSE: dict[int | str, dict[str, Any]] = {
    422: {"description": "The range starts after the day it ends."}
}
_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {
        "model": RunConflictOut,
        "description": (
            f"{_REFUSED} Or, with its typed conflict, the Agent already has a Suggestion run or "
            "an Evaluation Run in progress."
        ),
    },
    **_RANGE_RESPONSE,
}
_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {"model": ErrorResponse, "description": _REFUSED},
    **_RANGE_RESPONSE,
}
_CANCEL_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {"model": ErrorResponse, "description": SUGGESTION_FINISHED},
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


class SuggestionCostOut(BaseModel):
    # In US dollars. The estimate shown before it started: proposing, and checking (null without
    # an Evaluation Set, or when a price it needed is unknown).
    estimated_proposing_usd: Decimal | None
    estimated_checking_usd: Decimal | None
    # What proposing actually cost, frozen when it was spent; null until then, or when the
    # Evaluation Model's price is unknown.
    proposing_usd: Decimal | None


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
    cost: SuggestionCostOut
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


class EvidenceCountOut(BaseModel):
    # The UTC days counted, both included.
    range_start: date
    range_end: date
    # Every piece of evidence the range holds, before the cap of 50 a run reads.
    total: int
    # How many pieces qualify as each kind; a reply can qualify as several.
    live_verdict: int
    thumbs_down: int
    low_rating: int
    evaluation_case: int
    # Fewer than 10 pieces: a Suggestion is likely to be noise. A warning; starting is allowed.
    likely_noise: bool


class SuggestionEstimateOut(BaseModel):
    evidence: EvidenceCountOut
    # How many pieces a run would read: the most recent, at most 50.
    evidence_used: int
    # In US dollars; null when a price it needs is unknown. Proposing is priced at the
    # Evaluation Model's prices for a fixed allowance per piece of evidence and for its output.
    proposing_usd: Decimal | None
    # Whether the Agent has an Evaluation Set, so a Suggestion with a configuration change is
    # checked against it: two sides, the Live Version and the Suggestion. Null without one.
    has_evaluation_set: bool
    checking_usd: Decimal | None
    total_usd: Decimal | None


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
        cost=SuggestionCostOut(
            estimated_proposing_usd=suggestion.estimated_proposing_cost_usd,
            estimated_checking_usd=suggestion.estimated_checking_cost_usd,
            proposing_usd=suggestion.proposing_cost_usd,
        ),
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


@contextmanager
def _refused() -> Iterator[None]:
    """Turns what refuses starting a run, or the dialog's reads, into its HTTP error."""
    try:
        yield
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


def _range(
    clock: ClockDep, range_start: date | None = None, range_end: date | None = None
) -> tuple[date, date]:
    """The range asked for: by default the last 14 UTC days, today included."""
    end = range_end or clock.now().date()
    start = range_start or end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, RANGE_BACKWARDS)
    return start, end


def _body_range(body: SuggestionRunIn, clock: ClockDep) -> tuple[date, date]:
    return _range(clock, body.range_start, body.range_end)


Range = Annotated[tuple[date, date], Depends(_range)]
BodyRange = Annotated[tuple[date, date], Depends(_body_range)]


def _count(start: date, end: date, counted: service.EvidenceCount) -> EvidenceCountOut:
    by_kind = counted.by_kind
    return EvidenceCountOut(
        range_start=start,
        range_end=end,
        total=counted.total,
        live_verdict=by_kind[EvidenceKind.LIVE_VERDICT],
        thumbs_down=by_kind[EvidenceKind.THUMBS_DOWN],
        low_rating=by_kind[EvidenceKind.LOW_RATING],
        evaluation_case=by_kind[EvidenceKind.EVALUATION_CASE],
        likely_noise=counted.likely_noise,
    )


async def _read(
    db: Db, scope: Scope, project_id: uuid.UUID, agent_id: uuid.UUID, suggestion_id: uuid.UUID
) -> SuggestionOut:
    try:
        read = await service.get_suggestion(db, scope, project_id, agent_id, suggestion_id)
    except (ProjectNotFoundError, AgentNotFoundError, service.SuggestionNotFoundError):
        raise not_found() from None
    return _out(read)


@router.get("/evidence", operation_id="countSuggestionEvidence", responses=_READ_RESPONSES)
async def count_suggestion_evidence(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    days: Range,
) -> EvidenceCountOut:
    """How much evidence a Suggestion run of the range would find, by kind and before the cap,
    for the run dialog: by default the last 14 UTC days. Refused as starting would be, except
    while a run is in progress."""
    start, end = days
    with _refused():
        found = await service.estimate_suggestion(
            db, scope, project_id, agent_id, range_start=start, range_end=end, now=clock.now()
        )
    return _count(start, end, found.evidence)


@router.post("/estimate", operation_id="estimateSuggestionRun", responses=_READ_RESPONSES)
async def estimate_suggestion_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    days: BodyRange,
) -> SuggestionEstimateOut:
    """The evidence a Suggestion run of the range would read and its estimated Cost, proposing
    and checking, shown before starting it. Nothing is started; refused as starting would be,
    except while a run is in progress."""
    start, end = days
    with _refused():
        found = await service.estimate_suggestion(
            db, scope, project_id, agent_id, range_start=start, range_end=end, now=clock.now()
        )
    return SuggestionEstimateOut(
        evidence=_count(start, end, found.evidence),
        evidence_used=found.evidence_used,
        proposing_usd=found.proposing_usd,
        has_evaluation_set=found.has_evaluation_set,
        checking_usd=found.checking_usd,
        total_usd=found.total_usd,
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startSuggestionRun",
    response_model=SuggestionOut,
    responses=_START_RESPONSES,
)
async def start_suggestion_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    days: BodyRange,
) -> SuggestionOut | JSONResponse:
    """Starts a Suggestion run of the Agent's Live Version over the range, storing its estimated
    Cost. Poll the Suggestion until it is no longer in progress."""
    start, end = days
    try:
        with _refused():
            suggestion_id = await service.start_suggestion(
                db, scope, project_id, agent_id, range_start=start, range_end=end, now=clock.now()
            )
    except service.SuggestionInProgressError:
        return run_conflict(RunConflict.SUGGESTION_RUN_IN_PROGRESS, SUGGESTION_IN_PROGRESS)
    except service.EvaluationRunInProgressError:
        return run_conflict(RunConflict.EVALUATION_RUN_IN_PROGRESS, EVALUATION_RUN_IN_PROGRESS)
    await enqueue_suggestion(suggestion_id)
    # When tasks run eagerly the run has moved on in other sessions: read it afresh.
    db.expire_all()
    return await _read(db, scope, project_id, agent_id, suggestion_id)


@router.post(
    "/{suggestion_id}/cancel", operation_id="cancelSuggestionRun", responses=_CANCEL_RESPONSES
)
async def cancel_suggestion_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> SuggestionOut:
    """Cancels a Suggestion run in progress, also an archived Agent's: it stops before its next
    phase and keeps what it spent."""
    try:
        await service.cancel_suggestion(
            db, scope, project_id, agent_id, suggestion_id, now=clock.now()
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.SuggestionNotFoundError):
        raise not_found() from None
    except service.SuggestionFinishedError:
        raise HTTPException(status.HTTP_409_CONFLICT, SUGGESTION_FINISHED) from None
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
