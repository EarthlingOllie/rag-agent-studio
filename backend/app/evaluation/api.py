"""Evaluation routes, under an Agent: its Evaluation Set (cases: list, create, read, update and
delete), and its Evaluation Runs (start, list, read with progress, and read results). Editors and
Owners may use them; another Organisation's Agents are not found.

A case needs at least one expectation; for now that is a Reference answer. An archived Agent's
set and Runs can be read, but its cases can't be changed and it starts no Run.

Starting a Run answers the set with the Draft alone, with the Project's Current Instructions
Version, in a background task: the Run is returned ``queued`` (or, when tasks run eagerly, already
finished) and the Studio polls it until it is ``completed`` or ``failed``. Its results hold each
case as the Run copied it, with the answer, its Verdicts with the judge's reasons, and its Trace.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, StringConstraints

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
from app.evaluation.models import (
    QUESTION_MAX,
    REFERENCE_ANSWER_MAX,
    EvaluationCase,
    EvaluationRun,
    EvaluationVerdict,
    VerdictOutcome,
)
from app.evaluation.tasks import enqueue_run
from app.playground.api import CREDENTIAL_GONE, NO_DEFAULT_MODEL, TraceOut
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}/evaluation",
    tags=["evaluation"],
)

NO_EXPECTATION = "An Evaluation Case needs at least one expectation: write a Reference answer."
EMPTY_SET = "Add an Evaluation Case before evaluating."

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
            "The Project or Agent is archived, the Evaluation Set is empty, there is no Default "
            "Model, or the Draft names a Provider Credential that no longer exists."
        ),
    },
}


class CaseIn(BaseModel):
    question: Question
    # What a good answer says; null or blank for none (then the case has no expectation).
    reference_answer: ReferenceAnswer | None = None


class CaseOut(BaseModel):
    id: uuid.UUID
    question: str
    reference_answer: str | None
    # ``written`` by an Editor, or ``from_message``.
    source: str
    created_at: datetime
    updated_at: datetime


class ProgressOut(BaseModel):
    # Answers given (or errored) out of all the Run gives.
    done: int
    total: int


class RunSideOut(BaseModel):
    # ``first`` or ``second``; the Draft running alone is the ``first``.
    position: str
    # ``draft`` or ``version``.
    kind: str
    draft_revision: int | None
    # The Project Instructions it answered with: an Instructions Version's number, or null for
    # none (the Project had no Instructions Version).
    instructions_version_number: int | None
    # The effective chat model it answered with.
    model_provider: str
    model_name: str


class RunOut(BaseModel):
    id: uuid.UUID
    # ``queued``, ``running``, ``completed`` or ``failed``.
    status: str
    created_at: datetime
    finished_at: datetime | None
    progress: ProgressOut
    # The model that judged its answers.
    judge_provider: str
    judge_model: str
    error_message: str | None
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
    # True when every Verdict passed; null for an error.
    passed: bool | None
    verdicts: list[VerdictOut]
    # The answer's Trace (its ``message_id`` is this result's ID); null for an error before
    # an answer.
    trace: TraceOut | None


class RunCaseOut(BaseModel):
    # The case it was copied from; null once that case is deleted.
    case_id: uuid.UUID | None
    # The question and Reference answer as the Run copied them when it started.
    question: str
    reference_answer: str | None
    results: list[CaseResultOut]


class RunResultsOut(BaseModel):
    run: RunOut
    cases: list[RunCaseOut]


def _case_out(case: EvaluationCase) -> CaseOut:
    return CaseOut(
        id=case.id,
        question=case.question,
        reference_answer=case.reference_answer,
        source=case.source,
        created_at=case.created_at,
        updated_at=case.updated_at,
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
        error_message=run.error_message,
        sides=[
            RunSideOut(
                position=side.position,
                kind=side.kind,
                draft_revision=side.draft_revision,
                instructions_version_number=(
                    None
                    if side.instructions_version_id is None
                    else detail.instructions_numbers[side.instructions_version_id]
                ),
                model_provider=side.chat_provider,
                model_name=side.chat_model,
            )
            for side in detail.sides
        ],
    )


def _passed(status_: str, verdicts: list[EvaluationVerdict]) -> bool | None:
    if status_ != "answered":
        return None
    return all(v.outcome == VerdictOutcome.PASS for v in verdicts)


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
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> RunOut:
    """Starts a Run of the Agent's Evaluation Set: the Draft alone, with the Current
    Instructions Version. Poll it until it is ``completed`` or ``failed``."""
    try:
        run = await service.start_run(db, scope, project_id, agent_id, now=clock.now())
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    except service.EmptySetError:
        raise HTTPException(status.HTTP_409_CONFLICT, EMPTY_SET) from None
    except NoDefaultModelError:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_DEFAULT_MODEL) from None
    except ProviderCredentialGoneError:
        raise HTTPException(status.HTTP_409_CONFLICT, CREDENTIAL_GONE) from None
    run_id = run.id
    await enqueue_run(run_id)
    # When tasks run eagerly the Run has moved on in another session: read it afresh.
    db.expire_all()
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
                results=[
                    CaseResultOut(
                        position=positions[judged.result.side_id],
                        repeat=judged.result.repeat,
                        status=judged.result.status,
                        error_reason=judged.result.error_reason,
                        answer=judged.result.answer,
                        passed=_passed(judged.result.status, judged.verdicts),
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
