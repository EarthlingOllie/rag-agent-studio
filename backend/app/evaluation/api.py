"""Evaluation routes, under an Agent: its Evaluation Set (cases: list with search and filters,
create, read, update, delete, copy from another Agent of the Project, and prefill a new case from
one of the Agent's Messages), and its Evaluation Runs (start, list, read with progress, and read
results). Editors and Owners may use them; another Organisation's Agents are not found.

A set holds at most 200 cases, enforced under a lock on the Agent. A case added from a Message
copies the question it answered (the Editor edits it before saving) and keeps no link to the
Conversation; it outlives the Retention Window (ADR-0016). Adding a case from a Message and
deleting a case are Audit Events; writing and editing cases are not.

A case needs at least one expectation: Expected sources (each a passage of up to 1,000 characters
of one of the Project's Documents), a Reference answer, or Expect Fallback Text, which can't be
combined with either of the others. An Expected source whose Document was deleted, or whose
passage no Chunk of its current Edition holds, is a Stale expectation: the case is flagged, and
Runs skip it, neither pass nor fail. An archived Agent's set and Runs can be read, but its cases
can't be changed and it starts no Run.

Starting a Run answers the set with two sides, the first and the second, each the Draft or one
of the Agent's Versions (by default the Live Version against the Draft, or the Draft alone while
the Agent has never been Published), as many times as the Organisation's Evaluation repeats, in a
background task. A Version answers with the Instructions it pins, the Draft with the Instructions
Version or Instructions Draft chosen (the Current Instructions Version by default). The Run is
returned ``queued`` (or, when tasks run eagerly, already finished) and the Studio polls it until
it is ``completed``, ``failed`` (every case errored), ``cancelled`` or ``interrupted`` (its worker
stopped, spec 21). An Agent has at most one queued or running Run: a second start is refused with
a conflict, and a Run in progress can be cancelled, keeping what it spent. An Interrupted Run
keeps its answers, Verdicts and Cost too; running it again is starting a Run with its sides. A
Run with a Draft side is ``stale`` once the Draft has a newer Draft revision.

Its results hold each case as the Run copied it, Regressions (pass on the first side, fail on the
second) first, then improvements, then the rest, with each repeat's answer on each side, its
Verdicts with the judge's reasons, and its Trace, and the case's result on each side: pass or
fail by majority of its answered repeats with the count, Unsteady when they disagree, or Error
when every repeat errored. Each side has an Evaluation score, which leaves Error cases out; each
case in the set shows its latest result.

The Evaluation summary for Publish says, for the Instructions Version the Publish dialog has
chosen, whether the Draft has been evaluated against the current Live Version with those
Instructions, and what that Run found. It is advisory: the Publish endpoint is unchanged.
"""

import enum
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from app.agents.api import (
    AGENT_ARCHIVED_RESPONSE,
    NOT_FOUND_RESPONSE,
    agent_archived,
    archived,
    not_found,
)
from app.agents.resolution import NoDefaultModelError, ProviderCredentialGoneError
from app.agents.service import AgentArchivedError, AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.documents.service import DocumentNotFoundError
from app.evaluation import from_message, service, summary
from app.evaluation.combining import Repeat, SideResult
from app.evaluation.models import (
    PASSAGE_MAX,
    QUESTION_MAX,
    REFERENCE_ANSWER_MAX,
    CaseSource,
    EvaluationCase,
    EvaluationRun,
    SideKind,
    VerdictOutcome,
)
from app.evaluation.tasks import enqueue_run
from app.playground.api import CREDENTIAL_GONE, NO_DEFAULT_MODEL, Dollars, TraceOut
from app.projects.instructions import InstructionsVersionNotFoundError
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}/evaluation",
    tags=["evaluation"],
)

NO_EXPECTATION = (
    "An Evaluation Case needs at least one expectation: an Expected source, a Reference answer "
    "or Expect Fallback Text."
)
FALLBACK_WITH_REFERENCE = (
    "Expect Fallback Text can't be combined with a Reference answer: clear the Reference answer "
    "or untick Expect Fallback Text."
)
FALLBACK_WITH_SOURCE = (
    "Expect Fallback Text can't be combined with an Expected source: remove the Expected sources "
    "or untick Expect Fallback Text."
)
SOURCE_DOCUMENT_NOT_FOUND = "Choose a Document of this Project for each Expected source."
SOURCE_AGENT_NOT_FOUND = "Choose another Agent of this Project to copy cases from."
SOURCE_CASE_NOT_FOUND = "Choose cases of the Agent you are copying from."
EMPTY_SET = "Add an Evaluation Case before evaluating."
VERSION_NOT_FOUND = "Choose the Draft or one of this Agent's Versions for each side."
SAME_SIDES = "Choose two different sides."
INSTRUCTIONS_NOT_FOUND = "Choose one of this Project's Instructions Versions."
RUN_IN_PROGRESS = (
    "This Agent already has an Evaluation Run in progress. Wait for it to finish, or cancel it."
)
SUGGESTION_RUN_IN_PROGRESS = (
    "This Agent has a Suggestion run in progress. Wait for it to finish, or cancel it, then "
    "evaluate."
)
RUN_FINISHED = "This Run has already finished."
MESSAGE_PURGED = "This Message's text has been purged, so it can't be added to the Evaluation Set."


def version_credential_gone(number: int) -> str:
    return (
        f"Version {number} uses a Provider Credential that no longer exists, so it can't be "
        "evaluated. Choose another side."
    )


ClockDep = Annotated[Clock, Depends(get_clock)]


class RunConflict(enum.StrEnum):
    """What an Agent already has in progress when a Run of either kind is refused: an Agent runs
    one Evaluation Run or Suggestion run at a time."""

    EVALUATION_RUN_IN_PROGRESS = "evaluation_run_in_progress"
    SUGGESTION_RUN_IN_PROGRESS = "suggestion_run_in_progress"


class RunConflictOut(BaseModel):
    detail: str
    # Set when the Agent already has an Evaluation Run or Suggestion run in progress; null for
    # every other conflict.
    conflict: RunConflict | None = None


def run_conflict(conflict: RunConflict, detail: str) -> JSONResponse:
    """The typed 409 for a Run of either kind refused while the Agent has one in progress."""
    body = RunConflictOut(detail=detail, conflict=conflict)
    return JSONResponse(body.model_dump(mode="json"), status.HTTP_409_CONFLICT)


Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)
]
ReferenceAnswer = Annotated[str, StringConstraints(max_length=REFERENCE_ANSWER_MAX)]
Passage = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PASSAGE_MAX)
]
# More than enough for a question whose answer spans a few Documents.
EXPECTED_SOURCES_MAX = 20

_CHANGE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    **AGENT_ARCHIVED_RESPONSE,
    422: {
        "description": (
            "The question is empty or too long, the case has no expectation, Expect Fallback "
            "Text is combined with another expectation, or an Expected source's passage is "
            "empty or too long or its Document isn't the Project's."
        )
    },
}
_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_CHANGE_RESPONSES,
    409: {
        "model": ErrorResponse,
        "description": "The Project or Agent is archived, or the Evaluation Set holds 200 cases.",
    },
}
_COPY_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_CREATE_RESPONSES,
    422: {
        "model": ErrorResponse,
        "description": (
            "The Agent copied from is this one or not of the Project, or a case isn't in its set."
        ),
    },
}
_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {
        "model": RunConflictOut,
        "description": (
            "The Project or Agent is archived, it already has an Evaluation Run or Suggestion run "
            "in progress (with its typed conflict), the Evaluation Set is empty, there is no "
            "Default Model, or a side names a Provider Credential that no longer exists."
        ),
    },
    422: {
        "model": ErrorResponse,
        "description": (
            "A side isn't the Draft or one of the Agent's Versions, the two sides are the same, "
            "or the chosen Instructions Version isn't the Project's."
        ),
    },
}
_ESTIMATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {
        "model": ErrorResponse,
        "description": (
            "The Project or Agent is archived, the Evaluation Set is empty, there is no Default "
            "Model, or a side names a Provider Credential that no longer exists."
        ),
    },
    422: _START_RESPONSES[422],
}
_CANCEL_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {"model": ErrorResponse, "description": "The Run has already finished."},
}


class ExpectedSourceIn(BaseModel):
    # One of the Project's Documents.
    document_id: uuid.UUID
    # A passage of it, as one of its current Chunks holds it (case and whitespace aside).
    passage: Passage


class CaseIn(BaseModel):
    question: Question
    # What a good answer says; null or blank for none.
    reference_answer: ReferenceAnswer | None = None
    # Passages a good answer retrieves and cites.
    expected_sources: list[ExpectedSourceIn] = Field(
        default_factory=list, max_length=EXPECTED_SOURCES_MAX
    )
    # A good answer is the Fallback Text (or the Refusal text); never with a Reference answer
    # or an Expected source.
    expect_fallback: bool = False


class NewCaseIn(CaseIn):
    # ``written`` in the case editor, or ``from_message`` when prefilled from an Agent Message
    # (an Audit Event).
    source: Literal["written", "from_message"] = "written"


class CopyIn(BaseModel):
    # Another Agent of the same Project.
    agent_id: uuid.UUID
    # Cases of its Evaluation Set to copy.
    case_ids: list[uuid.UUID] = Field(min_length=1, max_length=service.CASES_MAX)


class ExpectedSourceOut(BaseModel):
    id: uuid.UUID
    # Null once the Document is deleted; its name stays.
    document_id: uuid.UUID | None
    document_name: str
    passage: str
    # Whether it is a Stale expectation, and why: ``document_deleted`` or ``passage_missing``.
    stale: bool
    stale_reason: str | None


class OfferedSourceOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    # The cited Chunk's text, up to a passage's length.
    passage: str


class PrefillOut(BaseModel):
    # The question the Message answered, to edit before saving.
    question: str
    # The passages the Message cited, offered as Expected sources.
    expected_sources: list[OfferedSourceOut]


class SideIn(BaseModel):
    # ``draft``, or ``version`` with the Agent Version's ``version_id``.
    kind: Literal["draft", "version"]
    version_id: uuid.UUID | None = None


class RunIn(BaseModel):
    # The first side, then the second; one side runs alone. Left out: the Live Version against
    # the Draft, or the Draft alone while the Agent has never been Published.
    sides: list[SideIn] | None = Field(default=None, min_length=1, max_length=2)
    # The Instructions the Draft side answers with: this Instructions Version of the Project,
    # else the Instructions Draft when ``instructions_draft``, else the Current Instructions
    # Version. A Version side always answers with the Instructions it pins.
    instructions_version_id: uuid.UUID | None = None
    instructions_draft: bool = False


class CaseSideResultOut(BaseModel):
    """A case's result on one side of a Run, from its repeats."""

    # ``pass`` or ``fail`` by majority of its answered repeats; ``error`` when every repeat
    # errored (then the case is left out of the side's Evaluation score).
    outcome: str
    # Answered repeats that passed, out of those answered (for example 2/3), and how many
    # repeats there were.
    passed: int
    answered: int
    repeats: int


class LatestResultOut(CaseSideResultOut):
    # The latest finished Run that answered the case.
    run_id: uuid.UUID
    # Whether its repeats disagreed.
    unsteady: bool


class CaseOut(BaseModel):
    id: uuid.UUID
    question: str
    reference_answer: str | None
    expected_sources: list[ExpectedSourceOut]
    expect_fallback: bool
    # Whether it has a Stale expectation.
    stale: bool
    # ``written`` by an Editor, or ``from_message``.
    source: str
    created_at: datetime
    updated_at: datetime
    # Its result in the latest finished Run that answered it; null until one has.
    latest_result: LatestResultOut | None


class ProgressOut(BaseModel):
    # Answers given (or errored) out of all the Run gives.
    done: int
    total: int


class RunSideOut(BaseModel):
    # ``first`` or ``second``; the Draft running alone is the ``first``.
    position: str
    # ``draft``, ``version``, ``rollout``: a Rollout evaluation's second side, the Version's
    # AgentConfig answering with the new Instructions Version, or ``suggestion``: a Suggestion's
    # check's second side, the Version's AgentConfig with the suggested changes.
    kind: str
    # The Agent Version, for a ``version``, ``rollout`` or ``suggestion`` side.
    agent_version_id: uuid.UUID | None
    version_number: int | None
    # The Draft revision it ran, for a ``draft`` side.
    draft_revision: int | None
    # The Project Instructions it answered with: an Instructions Version's number, or the
    # Instructions Draft (``instructions_draft``), or neither for none (the Project had no
    # Instructions Version).
    instructions_version_number: int | None
    instructions_draft: bool
    # The effective chat model it answered with.
    model_provider: str
    model_name: str
    # Its cases that passed, failed and were Errors, from those answered so far, and its
    # Evaluation score: the share of the cases that weren't Errors that passed (null with none).
    cases_passed: int
    cases_failed: int
    cases_errored: int
    score: float | None


class EstimateOut(BaseModel):
    """What a Run is expected to cost: the cases, times the sides, times the repeats, times each
    side's mean Cost per reply over the last 30 days (its model's prices and a fixed token
    allowance with no history), plus judging every answer at the judge's prices and the same
    allowance."""

    cases: int
    sides: int
    repeats: int
    # In US dollars; null when a price it needs is unknown.
    answers_usd: Dollars | None
    judging_usd: Dollars | None
    total_usd: Dollars | None


class RunCostOut(BaseModel):
    # The estimate shown before it started; null when a price it needed was unknown.
    estimated_usd: Dollars | None
    # What it actually cost so far, at the prices frozen as each answer and judgement ran.
    answers_usd: Dollars
    judging_usd: Dollars
    total_usd: Dollars


class RunOut(BaseModel):
    id: uuid.UUID
    # ``agent`` (started from the Agent), ``rollout`` (started by Rollout evaluation) or
    # ``suggestion`` (a Suggestion's check, started by its Suggestion run).
    kind: str
    # ``queued``, ``running``, ``completed``, ``failed``, ``cancelled`` or ``interrupted`` (its
    # worker stopped; what it answered and spent is kept, as for ``cancelled``).
    status: str
    created_at: datetime
    finished_at: datetime | None
    progress: ProgressOut
    # The model that judged its answers (the Evaluation Model, or else the Default Model) and
    # the Evaluation repeats, as they were when it started.
    judge_provider: str
    judge_model: str
    repeats: int
    error_message: str | None
    # Whether it has a Draft side and the Draft has a newer Draft revision since.
    stale: bool
    sides: list[RunSideOut]
    cost: RunCostOut


class VerdictOut(BaseModel):
    # ``expected_source``, ``fallback``, ``reference_answer`` or ``grounding``.
    kind: str
    # ``pass`` or ``fail``, or ``stale`` for a Stale expectation (skipped: neither).
    outcome: str
    # Why: the judge's one-sentence reason, or what the check found.
    reason: str | None


class CaseResultOut(BaseModel):
    position: str
    repeat: int
    # ``answered``, or ``error`` with its ``error_reason``.
    status: str
    error_reason: str | None
    answer: str | None
    # True when no Verdict failed; null for an error.
    passed: bool | None
    verdicts: list[VerdictOut]
    # The answer's Trace (its ``message_id`` is this result's ID); null for an error before
    # an answer.
    trace: TraceOut | None


class CaseSideOut(CaseSideResultOut):
    position: str


class RunExpectedSourceOut(BaseModel):
    document_name: str
    passage: str


class RunCaseOut(BaseModel):
    # The case as the Run copied it: where a Suggestion's evidence opens its result.
    id: uuid.UUID
    # The case it was copied from; null once that case is deleted.
    case_id: uuid.UUID | None
    # The question and expectations as the Run copied them when it started.
    question: str
    reference_answer: str | None
    expected_sources: list[RunExpectedSourceOut]
    expect_fallback: bool
    # Whether an answer skipped a Stale expectation.
    stale_expectation: bool
    # Its result on each side that has answered it.
    sides: list[CaseSideOut]
    # Whether its repeats disagreed on either side.
    unsteady: bool
    # ``regression`` (passes on the first side, fails on the second), ``improvement`` (the
    # reverse), or null.
    change: str | None
    # Every repeat's answer, on every side.
    results: list[CaseResultOut]


class RunResultsOut(BaseModel):
    run: RunOut
    # Regressions first, then improvements, then the rest, each in set order.
    cases: list[RunCaseOut]


def _side_fields(result: SideResult) -> dict[str, Any]:
    return {
        "outcome": result.outcome,
        "passed": result.passed,
        "answered": result.answered,
        "repeats": result.repeats,
    }


def _case_out(found: service.CaseWithResult) -> CaseOut:
    case: EvaluationCase = found.case
    latest = found.latest
    return CaseOut(
        id=case.id,
        question=case.question,
        reference_answer=case.reference_answer,
        expected_sources=[
            ExpectedSourceOut(
                id=expected.id,
                document_id=expected.document_id,
                document_name=expected.document_name,
                passage=expected.passage,
                stale=expected.stale,
                stale_reason=expected.stale_reason,
            )
            for expected in found.sources
        ],
        expect_fallback=case.expect_fallback,
        stale=found.stale,
        source=case.source,
        created_at=case.created_at,
        updated_at=case.updated_at,
        latest_result=None
        if latest is None
        else LatestResultOut(
            run_id=latest.run_id, unsteady=latest.result.unsteady, **_side_fields(latest.result)
        ),
    )


def _run_out(detail: service.RunDetail) -> RunOut:
    run: EvaluationRun = detail.run
    return RunOut(
        id=run.id,
        kind=run.kind,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
        progress=ProgressOut(done=run.answers_done, total=run.answers_total),
        judge_provider=run.judge_provider,
        judge_model=run.judge_model,
        repeats=run.repeats,
        error_message=run.error_message,
        stale=detail.stale,
        cost=RunCostOut(
            estimated_usd=run.estimated_cost_usd,
            answers_usd=detail.answers_cost_usd,
            judging_usd=detail.judging_cost_usd,
            total_usd=detail.answers_cost_usd + detail.judging_cost_usd,
        ),
        sides=[
            RunSideOut(
                position=side.position,
                kind=side.kind,
                agent_version_id=side.agent_version_id,
                version_number=(
                    None
                    if side.agent_version_id is None
                    else detail.version_numbers[side.agent_version_id]
                ),
                draft_revision=side.draft_revision,
                instructions_draft=side.instructions_draft,
                instructions_version_number=(
                    None
                    if side.instructions_version_id is None
                    else detail.instructions_numbers[side.instructions_version_id]
                ),
                model_provider=side.chat_provider,
                model_name=side.chat_model,
                cases_passed=detail.scores[side.id].passed,
                cases_failed=detail.scores[side.id].failed,
                cases_errored=detail.scores[side.id].errored,
                score=detail.scores[side.id].score,
            )
            for side in detail.sides
        ],
    )


def _passed(judged: service.JudgedResult) -> bool | None:
    repeat = Repeat(judged.result, judged.verdicts)
    return repeat.passed if repeat.answered else None


def _fields(body: CaseIn) -> service.CaseFields:
    return service.CaseFields(
        body.question,
        body.reference_answer,
        body.expect_fallback,
        [service.SourceFields(s.document_id, s.passage) for s in body.expected_sources],
    )


_INVALID: dict[type[Exception], str] = {
    service.NoExpectationError: NO_EXPECTATION,
    service.FallbackWithReferenceError: FALLBACK_WITH_REFERENCE,
    service.FallbackWithSourceError: FALLBACK_WITH_SOURCE,
    service.SourceDocumentNotFoundError: SOURCE_DOCUMENT_NOT_FOUND,
    service.SourceAgentNotFoundError: SOURCE_AGENT_NOT_FOUND,
    service.SourceCaseNotFoundError: SOURCE_CASE_NOT_FOUND,
}


def case_limit(held: int) -> str:
    return (
        f"An Evaluation Set holds at most {service.CASES_MAX} cases, and this one has "
        f"{held}. Delete cases before adding more."
    )


def _change_refused(error: Exception) -> HTTPException:
    if isinstance(error, service.CaseLimitError):
        return HTTPException(status.HTTP_409_CONFLICT, case_limit(error.held))
    if isinstance(error, ProjectArchivedError):
        return archived()
    if isinstance(error, AgentArchivedError):
        return agent_archived()
    if type(error) in _INVALID:
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _INVALID[type(error)])
    return not_found()


_NOT_FOUND = (
    ProjectNotFoundError,
    AgentNotFoundError,
    service.CaseNotFoundError,
    service.RunNotFoundError,
)
_REFUSED: tuple[type[Exception], ...] = (
    *_NOT_FOUND,
    ProjectArchivedError,
    AgentArchivedError,
    service.CaseLimitError,
    *_INVALID,
)


@router.get("/cases", operation_id="listEvaluationCases", responses=NOT_FOUND_RESPONSE)
async def list_cases(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    q: Annotated[str | None, Query(max_length=QUESTION_MAX)] = None,
    kind: service.ExpectationKind | None = None,
    stale: bool | None = None,
    result: service.LatestKind | None = None,
) -> list[CaseOut]:
    """The Agent's Evaluation Set, oldest case first: with ``q``, the cases whose question
    holds it (letter case aside); with ``kind``, those with that kind of expectation; with
    ``stale``, those with (or without) a Stale expectation; with ``result``, those whose latest
    result is ``pass``, ``fail``, ``unsteady`` (its repeats disagreed), ``error``, or
    ``not_run``."""
    where = service.CaseFilter((q or "").strip() or None, kind, stale, result)
    try:
        cases = await service.list_cases(db, scope, project_id, agent_id, where)
    except _NOT_FOUND:
        raise not_found() from None
    return [_case_out(case) for case in cases]


@router.post(
    "/cases",
    status_code=status.HTTP_201_CREATED,
    operation_id="createEvaluationCase",
    responses=_CREATE_RESPONSES,
)
async def create_case(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: NewCaseIn,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> CaseOut:
    """Adds a case to the Agent's Evaluation Set, of at most 200. A case added from a Message
    is an Audit Event."""
    try:
        case = await service.create_case(
            db,
            scope,
            project_id,
            agent_id,
            _fields(body),
            source=CaseSource(body.source),
            now=clock.now(),
        )
    except _REFUSED as error:
        raise _change_refused(error) from None
    return _case_out(case)


@router.post(
    "/cases/copy",
    status_code=status.HTTP_201_CREATED,
    operation_id="copyEvaluationCases",
    responses=_COPY_RESPONSES,
)
async def copy_cases(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: CopyIn,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> list[CaseOut]:
    """Copies cases of another Agent of the Project into this Agent's Evaluation Set, as
    independent copies, in their set's order; the copies are returned."""
    try:
        copies = await service.copy_cases(
            db, scope, project_id, agent_id, body.agent_id, body.case_ids, now=clock.now()
        )
    except _REFUSED as error:
        raise _change_refused(error) from None
    return [_case_out(case) for case in copies]


@router.get("/cases/{case_id}", operation_id="getEvaluationCase", responses=NOT_FOUND_RESPONSE)
async def get_case(
    project_id: uuid.UUID, agent_id: uuid.UUID, case_id: uuid.UUID, scope: Scope, db: Db
) -> CaseOut:
    try:
        case = await service.get_case(db, scope, project_id, agent_id, case_id)
    except _NOT_FOUND:
        raise not_found() from None
    return _case_out(case)


@router.put("/cases/{case_id}", operation_id="updateEvaluationCase", responses=_CHANGE_RESPONSES)
async def update_case(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
    body: CaseIn,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> CaseOut:
    """Replaces the case's question and expectations; past Runs keep their copies."""
    try:
        case = await service.update_case(
            db, scope, project_id, agent_id, case_id, _fields(body), now=clock.now()
        )
    except _REFUSED as error:
        raise _change_refused(error) from None
    return _case_out(case)


@router.delete(
    "/cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteEvaluationCase",
    responses={**NOT_FOUND_RESPONSE, **AGENT_ARCHIVED_RESPONSE},
)
async def delete_case(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> Response:
    """Deletes the case, an Audit Event; past Runs keep their copies."""
    try:
        await service.delete_case(db, scope, project_id, agent_id, case_id, now=clock.now())
    except _REFUSED as error:
        raise _change_refused(error) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/messages/{message_id}/prefill",
    operation_id="prefillEvaluationCase",
    responses={
        **NOT_FOUND_RESPONSE,
        409: {"model": ErrorResponse, "description": "The Message's text has been purged."},
    },
)
async def prefill_case(
    project_id: uuid.UUID, agent_id: uuid.UUID, message_id: uuid.UUID, scope: Scope, db: Db
) -> PrefillOut:
    """A new case from one of the Agent's replies, in the Conversations viewer or the
    Playground: the question it answered and the passages it cited. Nothing is saved, and a case
    keeps no link to the Conversation. Refused once the text has been purged."""
    try:
        found = await from_message.prefill(db, scope, project_id, agent_id, message_id)
    except (ProjectNotFoundError, AgentNotFoundError, from_message.MessageNotFoundError):
        raise not_found() from None
    except from_message.MessagePurgedError:
        raise HTTPException(status.HTTP_409_CONFLICT, MESSAGE_PURGED) from None
    return PrefillOut(
        question=found.question,
        expected_sources=[
            OfferedSourceOut(
                document_id=each.document_id, document_name=each.document_name, passage=each.passage
            )
            for each in found.expected_sources
        ],
    )


def _choices(choice: RunIn) -> dict[str, Any]:
    return {
        "sides": None
        if choice.sides is None
        else [service.SideChoice(SideKind(side.kind), side.version_id) for side in choice.sides],
        "instructions_version_id": choice.instructions_version_id,
        "instructions_draft": choice.instructions_draft,
    }


@contextmanager
def _start_refused() -> Iterator[None]:
    """Turns what refuses starting (or estimating) a Run into its HTTP error."""
    try:
        yield
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    except service.RunInProgressError:
        # Only starting checks it; the caller answers with the typed conflict.
        raise
    except service.EmptySetError:
        raise HTTPException(status.HTTP_409_CONFLICT, EMPTY_SET) from None
    except service.VersionNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, VERSION_NOT_FOUND) from None
    except service.SameSidesError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, SAME_SIDES) from None
    except InstructionsVersionNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INSTRUCTIONS_NOT_FOUND) from None
    except NoDefaultModelError:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_DEFAULT_MODEL) from None
    except service.VersionCredentialGoneError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, version_credential_gone(error.number)
        ) from None
    except ProviderCredentialGoneError:
        raise HTTPException(status.HTTP_409_CONFLICT, CREDENTIAL_GONE) from None


@router.post("/estimate", operation_id="estimateEvaluationRun", responses=_ESTIMATE_RESPONSES)
async def estimate_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    body: RunIn | None = None,
) -> EstimateOut:
    """The estimated Cost of starting a Run with these choices now, shown before starting it.
    Nothing is started; refused as starting would be, except while a Run is in progress."""
    with _start_refused():
        found = await service.estimate_run(
            db, scope, project_id, agent_id, **_choices(body or RunIn()), now=clock.now()
        )
    return EstimateOut(
        cases=found.cases,
        sides=found.sides,
        repeats=found.repeats,
        answers_usd=found.answers_usd,
        judging_usd=found.judging_usd,
        total_usd=found.total_usd,
    )


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startEvaluationRun",
    response_model=RunOut,
    responses=_START_RESPONSES,
)
async def start_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    body: RunIn | None = None,
) -> RunOut | JSONResponse:
    """Starts a Run of the Agent's Evaluation Set, by default the Live Version against the Draft
    (the Draft alone while the Agent has never been Published), storing its estimated Cost. Poll
    it until it is ``completed``, ``failed``, ``cancelled`` or ``interrupted``."""
    try:
        with _start_refused():
            run = await service.start_run(
                db, scope, project_id, agent_id, **_choices(body or RunIn()), now=clock.now()
            )
    except service.SuggestionInProgressError:
        return run_conflict(RunConflict.SUGGESTION_RUN_IN_PROGRESS, SUGGESTION_RUN_IN_PROGRESS)
    except service.RunInProgressError:
        return run_conflict(RunConflict.EVALUATION_RUN_IN_PROGRESS, RUN_IN_PROGRESS)
    run_id = run.id
    await enqueue_run(run_id)
    # When tasks run eagerly the Run has moved on in another session: read it afresh.
    db.expire_all()
    return _run_out(await service.get_run(db, scope, project_id, agent_id, run_id))


@router.post(
    "/runs/{run_id}/cancel", operation_id="cancelEvaluationRun", responses=_CANCEL_RESPONSES
)
async def cancel_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> RunOut:
    """Cancels a queued or running Run: it stops before its next answer and keeps what it
    answered and spent."""
    try:
        await service.cancel_run(db, scope, project_id, agent_id, run_id, now=clock.now())
    except _NOT_FOUND:
        raise not_found() from None
    except service.RunFinishedError:
        raise HTTPException(status.HTTP_409_CONFLICT, RUN_FINISHED) from None
    return _run_out(await service.get_run(db, scope, project_id, agent_id, run_id))


@router.get("/runs", operation_id="listEvaluationRuns", responses=NOT_FOUND_RESPONSE)
async def list_runs(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> list[RunOut]:
    """The Agent's Runs, newest first."""
    try:
        runs = await service.list_runs(db, scope, project_id, agent_id)
    except _NOT_FOUND:
        raise not_found() from None
    return [
        _run_out(await service.get_run(db, scope, project_id, agent_id, run.id)) for run in runs
    ]


@router.get("/runs/{run_id}", operation_id="getEvaluationRun", responses=NOT_FOUND_RESPONSE)
async def get_run(
    project_id: uuid.UUID, agent_id: uuid.UUID, run_id: uuid.UUID, scope: Scope, db: Db
) -> RunOut:
    """The Run's status, progress and sides."""
    try:
        detail = await service.get_run(db, scope, project_id, agent_id, run_id)
    except _NOT_FOUND:
        raise not_found() from None
    return _run_out(detail)


@router.get(
    "/runs/{run_id}/results", operation_id="getEvaluationRunResults", responses=NOT_FOUND_RESPONSE
)
async def get_run_results(
    project_id: uuid.UUID, agent_id: uuid.UUID, run_id: uuid.UUID, scope: Scope, db: Db
) -> RunResultsOut:
    """Each case as the Run copied it, with every answer, its Verdicts and its Trace."""
    try:
        detail, cases = await service.run_results(db, scope, project_id, agent_id, run_id)
    except _NOT_FOUND:
        raise not_found() from None
    positions = {side.id: side.position for side in detail.sides}
    return RunResultsOut(
        run=_run_out(detail),
        cases=[
            RunCaseOut(
                id=case.case.id,
                case_id=case.case.case_id,
                question=case.case.question,
                reference_answer=case.case.reference_answer,
                expected_sources=[
                    RunExpectedSourceOut(
                        document_name=each["document_name"], passage=each["passage"]
                    )
                    for each in case.case.expected_sources
                ],
                expect_fallback=case.case.expect_fallback,
                stale_expectation=case.stale_expectation,
                sides=[
                    CaseSideOut(position=positions[side_id], **_side_fields(result))
                    for side_id, result in case.sides.items()
                ],
                unsteady=case.unsteady,
                change=case.change,
                results=[
                    CaseResultOut(
                        position=positions[judged.result.side_id],
                        repeat=judged.result.repeat,
                        status=judged.result.status,
                        error_reason=judged.result.error_reason,
                        answer=judged.result.answer,
                        passed=_passed(judged),
                        verdicts=[
                            VerdictOut(kind=v.kind, outcome=v.outcome, reason=v.reason)
                            for v in judged.verdicts
                        ],
                        trace=None
                        if judged.result.trace is None
                        else TraceOut.model_validate(judged.result.trace),
                    )
                    for judged in case.results
                ],
            )
            for case in cases
        ],
    )


class RegressionReasonOut(BaseModel):
    # The Verdict's kind and the judge's (or the check's) reason it failed.
    kind: str
    reason: str | None


class SummaryRegressionOut(BaseModel):
    # The case it was copied from; null once that case is deleted.
    case_id: uuid.UUID | None
    question: str
    # Why the Draft failed it: its failing Verdicts' reasons, each once.
    reasons: list[RegressionReasonOut]


class PublishSummaryOut(BaseModel):
    """Whether the Draft has been evaluated against the current Live Version with the
    Instructions being published. Advisory: Publishing never depends on it."""

    # ``no_set``, ``no_run``, ``live_changed``, ``stale``, ``instructions_differ``,
    # ``regressions`` or ``clear``.
    state: Literal[
        "no_set", "no_run", "live_changed", "stale", "instructions_differ", "regressions", "clear"
    ]
    # The latest completed Run of the Draft against the current Live Version (the Draft alone
    # while the Agent has never been Published), with its scores; null without one.
    run: RunOut | None
    # That Run's Regressions, in set order.
    regressions: list[SummaryRegressionOut]
    # Whether the Draft's Evaluation score is lower than the Live Version's in that Run.
    lower_score: bool
    # For ``live_changed``: the Version the Draft's latest Run was compared with.
    evaluated_live_version_number: int | None
    # The Instructions Version being published: the one chosen, else the Current one; null
    # when the Project has none.
    publishing_instructions_version_number: int | None


def _reasons(case: service.CaseResults, second: uuid.UUID) -> list[RegressionReasonOut]:
    seen: list[tuple[str, str | None]] = []
    for judged in case.results:
        if judged.result.side_id != second:
            continue
        for verdict in judged.verdicts:
            failing = (verdict.kind, verdict.reason)
            if verdict.outcome == VerdictOutcome.FAIL and failing not in seen:
                seen.append(failing)
    return [RegressionReasonOut(kind=kind, reason=reason) for kind, reason in seen]


@router.get(
    "/publish-summary",
    operation_id="getEvaluationPublishSummary",
    responses={
        **NOT_FOUND_RESPONSE,
        422: {
            "model": ErrorResponse,
            "description": "The chosen Instructions Version isn't the Project's.",
        },
    },
)
async def get_publish_summary(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    instructions_version_id: uuid.UUID | None = None,
) -> PublishSummaryOut:
    """The Evaluation summary the Publish dialog shows for publishing the Draft with
    ``instructions_version_id`` (the Current Instructions Version when left out). Only Runs of
    the Draft against the current Live Version qualify. The Publish endpoint is unchanged:
    its warnings never block Publishing."""
    try:
        found = await summary.publish_summary(
            db, scope, project_id, agent_id, instructions_version_id=instructions_version_id
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except InstructionsVersionNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INSTRUCTIONS_NOT_FOUND) from None
    run = found.run
    return PublishSummaryOut(
        state=found.state,
        run=None if run is None else _run_out(run),
        regressions=[]
        if run is None
        else [
            SummaryRegressionOut(
                case_id=case.case.case_id,
                question=case.case.question,
                reasons=_reasons(case, run.sides[-1].id),
            )
            for case in found.regressions
        ],
        lower_score=found.lower_score,
        evaluated_live_version_number=found.evaluated_live_version_number,
        publishing_instructions_version_number=found.publishing_instructions_version_number,
    )


documents_router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/documents/{document_id}",
    tags=["evaluation"],
)


class DependentAgentOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    case_count: int


class ExpectedSourceDependentsOut(BaseModel):
    agents: list[DependentAgentOut]
    passages: list[str]


@documents_router.get(
    "/expected-sources",
    operation_id="getExpectedSourceDependents",
    responses=NOT_FOUND_RESPONSE,
)
async def get_expected_source_dependents(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db
) -> ExpectedSourceDependentsOut:
    """The Agents, by name, and how many of their cases hold an Expected source in the Document
    (the Expected source warning before it is deleted or a new Edition uploaded), and the
    distinct passages used, for the Document viewer to mark."""
    try:
        found = await service.expected_source_dependents(db, scope, project_id, document_id)
    except (ProjectNotFoundError, DocumentNotFoundError):
        raise not_found() from None
    return ExpectedSourceDependentsOut(
        agents=[
            DependentAgentOut(agent_id=a.agent_id, name=a.name, case_count=a.case_count)
            for a in found.agents
        ],
        passages=found.passages,
    )
