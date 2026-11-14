"""Evaluation routes, under an Agent: its Evaluation Set (cases: list, create, read, update and
delete), and its Evaluation Runs (start, list, read with progress, and read results). Editors and
Owners may use them; another Organisation's Agents are not found.

A case needs at least one expectation; for now that is a Reference answer. An archived Agent's
set and Runs can be read, but its cases can't be changed and it starts no Run.

Starting a Run answers the set with two sides, the first and the second, each the Draft or one
of the Agent's Versions (by default the Live Version against the Draft, or the Draft alone while
the Agent has never been Published), as many times as the Organisation's Evaluation repeats, in a
background task. A Version answers with the Instructions it pins, the Draft with the Instructions
Version or Instructions Draft chosen (the Current Instructions Version by default). The Run is
returned ``queued`` (or, when tasks run eagerly, already finished) and the Studio polls it until
it is ``completed``, ``failed`` (every case errored) or ``cancelled``. An Agent has at most one
queued or running Run: a second start is refused with a conflict, and a Run in progress can be
cancelled, keeping what it spent. A Run with a Draft side is ``stale`` once the Draft has a newer
Draft revision.

Its results hold each case as the Run copied it, Regressions (pass on the first side, fail on the
second) first, then improvements, then the rest, with each repeat's answer on each side, its
Verdicts with the judge's reasons, and its Trace, and the case's result on each side: pass or
fail by majority of its answered repeats with the count, Unsteady when they disagree, or Error
when every repeat errored. Each side has an Evaluation score, which leaves Error cases out; each
case in the set shows its latest result.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from app.evaluation import service
from app.evaluation.combining import Repeat, SideResult
from app.evaluation.models import (
    QUESTION_MAX,
    REFERENCE_ANSWER_MAX,
    EvaluationCase,
    EvaluationRun,
    SideKind,
)
from app.evaluation.tasks import enqueue_run
from app.playground.api import CREDENTIAL_GONE, NO_DEFAULT_MODEL, TraceOut
from app.projects.instructions import InstructionsVersionNotFoundError
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}/evaluation",
    tags=["evaluation"],
)

NO_EXPECTATION = "An Evaluation Case needs at least one expectation: write a Reference answer."
EMPTY_SET = "Add an Evaluation Case before evaluating."
VERSION_NOT_FOUND = "Choose the Draft or one of this Agent's Versions for each side."
SAME_SIDES = "Choose two different sides."
INSTRUCTIONS_NOT_FOUND = "Choose one of this Project's Instructions Versions."
RUN_IN_PROGRESS = (
    "This Agent already has an Evaluation Run in progress. Wait for it to finish, or cancel it."
)
RUN_FINISHED = "This Run has already finished."


def version_credential_gone(number: int) -> str:
    return (
        f"Version {number} uses a Provider Credential that no longer exists, so it can't be "
        "evaluated. Choose another side."
    )


ClockDep = Annotated[Clock, Depends(get_clock)]
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)
]
ReferenceAnswer = Annotated[str, StringConstraints(max_length=REFERENCE_ANSWER_MAX)]

_CHANGE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    **AGENT_ARCHIVED_RESPONSE,
    422: {"description": "The question is empty or too long, or the case has no expectation."},
}
_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {
        "model": ErrorResponse,
        "description": (
            "The Project or Agent is archived, it already has a Run in progress, the Evaluation "
            "Set is empty, there is no Default Model, or a side names a Provider Credential that "
            "no longer exists."
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
_CANCEL_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    409: {"model": ErrorResponse, "description": "The Run has already finished."},
}


class CaseIn(BaseModel):
    question: Question
    # What a good answer says; null or blank for none (then the case has no expectation).
    reference_answer: ReferenceAnswer | None = None


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
    # ``draft`` or ``version``.
    kind: str
    # The Agent Version, for a ``version`` side.
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


class RunOut(BaseModel):
    id: uuid.UUID
    # ``queued``, ``running``, ``completed``, ``failed`` or ``cancelled``.
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


class VerdictOut(BaseModel):
    # ``reference_answer`` or ``grounding``.
    kind: str
    # ``pass`` or ``fail``.
    outcome: str
    # The judge's one-sentence reason.
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


class RunCaseOut(BaseModel):
    # The case it was copied from; null once that case is deleted.
    case_id: uuid.UUID | None
    # The question and Reference answer as the Run copied them when it started.
    question: str
    reference_answer: str | None
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
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
        progress=ProgressOut(done=run.answers_done, total=run.answers_total),
        judge_provider=run.judge_provider,
        judge_model=run.judge_model,
        repeats=run.repeats,
        error_message=run.error_message,
        stale=detail.stale,
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
    return service.CaseFields(body.question, body.reference_answer)


def _change_refused(error: Exception) -> HTTPException:
    if isinstance(error, ProjectArchivedError):
        return archived()
    if isinstance(error, AgentArchivedError):
        return agent_archived()
    if isinstance(error, service.NoExpectationError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_EXPECTATION)
    return not_found()


_NOT_FOUND = (
    ProjectNotFoundError,
    AgentNotFoundError,
    service.CaseNotFoundError,
    service.RunNotFoundError,
)
_REFUSED = (*_NOT_FOUND, ProjectArchivedError, AgentArchivedError, service.NoExpectationError)


@router.get("/cases", operation_id="listEvaluationCases", responses=NOT_FOUND_RESPONSE)
async def list_cases(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> list[CaseOut]:
    """The Agent's Evaluation Set, oldest case first."""
    try:
        cases = await service.list_cases(db, scope, project_id, agent_id)
    except _NOT_FOUND:
        raise not_found() from None
    return [_case_out(case) for case in cases]


@router.post(
    "/cases",
    status_code=status.HTTP_201_CREATED,
    operation_id="createEvaluationCase",
    responses=_CHANGE_RESPONSES,
)
async def create_case(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: CaseIn,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> CaseOut:
    """Adds a case to the Agent's Evaluation Set."""
    try:
        case = await service.create_case(
            db, scope, project_id, agent_id, _fields(body), now=clock.now()
        )
    except _REFUSED as error:
        raise _change_refused(error) from None
    return _case_out(case)


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
    project_id: uuid.UUID, agent_id: uuid.UUID, case_id: uuid.UUID, scope: Scope, db: Db
) -> Response:
    """Deletes the case; past Runs keep their copies."""
    try:
        await service.delete_case(db, scope, project_id, agent_id, case_id)
    except _REFUSED as error:
        raise _change_refused(error) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startEvaluationRun",
    responses=_START_RESPONSES,
)
async def start_run(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    body: RunIn | None = None,
) -> RunOut:
    """Starts a Run of the Agent's Evaluation Set, by default the Live Version against the Draft
    (the Draft alone while the Agent has never been Published). Poll it until it is
    ``completed``, ``failed`` or ``cancelled``."""
    choice = body or RunIn()
    try:
        run = await service.start_run(
            db,
            scope,
            project_id,
            agent_id,
            sides=None
            if choice.sides is None
            else [
                service.SideChoice(SideKind(side.kind), side.version_id) for side in choice.sides
            ],
            instructions_version_id=choice.instructions_version_id,
            instructions_draft=choice.instructions_draft,
            now=clock.now(),
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    except service.RunInProgressError:
        raise HTTPException(status.HTTP_409_CONFLICT, RUN_IN_PROGRESS) from None
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
                case_id=case.case.case_id,
                question=case.case.question,
                reference_answer=case.case.reference_answer,
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
