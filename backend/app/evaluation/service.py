"""An Agent's Evaluation Set (its cases) and starting and reading its Evaluation Runs.

Every function takes an ``OrganisationScope`` and the Project and Agent IDs, so a case or a Run
is only found inside its own Agent of the Organisation the Member works in. An archived Agent's
set and Runs stay readable; its cases can't be changed and it starts no Run.

Starting a Run (for now: the Draft alone, with the Current Instructions Version) resolves the
Draft's models as a Visitor reply would (``app.agents.resolution``) and the judge (the Default
Model), snapshots the side and every case, and leaves the Run ``queued`` for its task
(``app.evaluation.job``). The caller enqueues the task once the Run is committed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resolution import NoDefaultModelError, resolve_models
from app.agents.service import AgentWithDraft, active_agent, get_agent
from app.default_model.service import read_default
from app.evaluation.models import (
    CaseSource,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunCase,
    EvaluationRunSide,
    EvaluationVerdict,
    RunStatus,
    SideKind,
)
from app.projects.models import InstructionsVersion
from app.projects.service import active_project
from app.tenancy.repository import OrganisationScope

FIRST = "first"


class CaseNotFoundError(Exception):
    """No Evaluation Case with that ID in the Agent's set."""


class RunNotFoundError(Exception):
    """No Evaluation Run with that ID for the Agent."""


class NoExpectationError(Exception):
    """An Evaluation Case needs at least one expectation."""


class EmptySetError(Exception):
    """A Run needs at least one Evaluation Case."""


@dataclass(frozen=True)
class CaseFields:
    question: str
    # None or blank: no Reference answer.
    reference_answer: str | None


def _checked(fields: CaseFields) -> CaseFields:
    reference = (fields.reference_answer or "").strip() or None
    if reference is None:
        raise NoExpectationError
    return CaseFields(fields.question, reference)


async def _agent(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    change: bool,
) -> AgentWithDraft:
    """The Agent; to change its set, refused while it or its Project is archived."""
    if not change:
        return await get_agent(session, scope, project_id, agent_id)
    await active_project(session, scope, project_id)
    return await active_agent(session, scope, project_id, agent_id, lock=True)


async def list_cases(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> list[EvaluationCase]:
    """The Agent's Evaluation Set, oldest case first."""
    found = await _agent(session, scope, project_id, agent_id, change=False)
    cases = await session.scalars(
        select(EvaluationCase)
        .where(EvaluationCase.agent_id == found.agent.id)
        .order_by(EvaluationCase.created_at, EvaluationCase.id)
    )
    return list(cases)


async def _case(session: AsyncSession, agent_id: uuid.UUID, case_id: uuid.UUID) -> EvaluationCase:
    case = await session.scalar(
        select(EvaluationCase).where(
            EvaluationCase.id == case_id, EvaluationCase.agent_id == agent_id
        )
    )
    if case is None:
        raise CaseNotFoundError
    return case


async def get_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
) -> EvaluationCase:
    found = await _agent(session, scope, project_id, agent_id, change=False)
    return await _case(session, found.agent.id, case_id)


async def create_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    fields: CaseFields,
    *,
    now: datetime,
) -> EvaluationCase:
    """Adds a written case; refused with ``NoExpectationError`` without an expectation."""
    checked = _checked(fields)
    found = await _agent(session, scope, project_id, agent_id, change=True)
    case = EvaluationCase(
        organisation_id=scope.organisation_id,
        agent_id=found.agent.id,
        question=checked.question,
        reference_answer=checked.reference_answer,
        source=CaseSource.WRITTEN,
        created_by=scope.member_id,
        created_at=now,
        updated_at=now,
    )
    session.add(case)
    await session.commit()
    return case


async def update_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
    fields: CaseFields,
    *,
    now: datetime,
) -> EvaluationCase:
    """Replaces the case's question and expectations. Past Runs keep their copies."""
    checked = _checked(fields)
    found = await _agent(session, scope, project_id, agent_id, change=True)
    case = await _case(session, found.agent.id, case_id)
    case.question = checked.question
    case.reference_answer = checked.reference_answer
    case.updated_at = now
    await session.commit()
    return case


async def delete_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
) -> None:
    """Deletes the case. Past Runs keep their copies of it."""
    found = await _agent(session, scope, project_id, agent_id, change=True)
    case = await _case(session, found.agent.id, case_id)
    await session.delete(case)
    await session.commit()


async def start_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> EvaluationRun:
    """A queued Run of the Draft alone, with the Project's Current Instructions Version (no
    Project Instructions while it has none). Refused for an archived Agent, an empty set
    (``EmptySetError``), a Draft that can't be resolved (``NoDefaultModelError``,
    ``ProviderCredentialGoneError``) and an Organisation without a Default Model to judge."""
    project = await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id, lock=True)
    cases = await list_cases(session, scope, project_id, agent_id)
    if not cases:
        raise EmptySetError
    resolved = await resolve_models(session, scope.organisation_id, found.draft)
    judge = await read_default(session, scope.organisation_id)
    if judge is None:
        raise NoDefaultModelError
    instructions = (
        None
        if project.current_instructions_version_id is None
        else await session.get_one(InstructionsVersion, project.current_instructions_version_id)
    )
    run = EvaluationRun(
        organisation_id=scope.organisation_id,
        agent_id=found.agent.id,
        status=RunStatus.QUEUED,
        started_by=scope.member_id,
        judge_credential_id=judge.credential.id,
        judge_provider=judge.credential.provider,
        judge_model=judge.model,
        answers_done=0,
        answers_total=len(cases),
        created_at=now,
    )
    session.add(run)
    await session.flush()
    session.add(
        EvaluationRunSide(
            organisation_id=scope.organisation_id,
            run_id=run.id,
            position=FIRST,
            kind=SideKind.DRAFT,
            draft_revision=found.draft_revision,
            instructions_version_id=None if instructions is None else instructions.id,
            instructions_draft=False,
            instructions="" if instructions is None else instructions.markdown,
            config=resolved.config.model_dump(mode="json"),
            chat_provider=resolved.chat.credential.provider,
            chat_model=resolved.chat.model,
            automatic_fallback=resolved.automatic_fallback,
        )
    )
    session.add_all(
        EvaluationRunCase(
            organisation_id=scope.organisation_id,
            run_id=run.id,
            case_id=case.id,
            position=position,
            question=case.question,
            reference_answer=case.reference_answer,
        )
        for position, case in enumerate(cases)
    )
    await session.commit()
    return run


async def list_runs(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> list[EvaluationRun]:
    """The Agent's Runs, newest first."""
    found = await _agent(session, scope, project_id, agent_id, change=False)
    runs = await session.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.agent_id == found.agent.id)
        .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id)
    )
    return list(runs)


@dataclass(frozen=True)
class RunDetail:
    run: EvaluationRun
    sides: list[EvaluationRunSide]
    # The Instructions Versions' numbers, by ID.
    instructions_numbers: dict[uuid.UUID, int]


async def get_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
) -> RunDetail:
    found = await _agent(session, scope, project_id, agent_id, change=False)
    run = await session.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id, EvaluationRun.agent_id == found.agent.id
        )
    )
    if run is None:
        raise RunNotFoundError
    sides = list(
        await session.scalars(
            select(EvaluationRunSide)
            .where(EvaluationRunSide.run_id == run.id)
            .order_by(EvaluationRunSide.position)
        )
    )
    versions = {s.instructions_version_id for s in sides if s.instructions_version_id}
    numbers = await session.execute(
        select(InstructionsVersion.id, InstructionsVersion.number).where(
            InstructionsVersion.id.in_(versions)
        )
    )
    return RunDetail(run, sides, {row.id: row.number for row in numbers})


@dataclass(frozen=True)
class JudgedResult:
    result: EvaluationCaseResult
    verdicts: list[EvaluationVerdict]


@dataclass(frozen=True)
class CaseResults:
    """A case as the Run copied it, with each side's answers."""

    case: EvaluationRunCase
    results: list[JudgedResult]


async def run_results(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
) -> tuple[RunDetail, list[CaseResults]]:
    """The Run's cases in set order, each with its answers and their Verdicts."""
    detail = await get_run(session, scope, project_id, agent_id, run_id)
    cases = await session.scalars(
        select(EvaluationRunCase)
        .where(EvaluationRunCase.run_id == run_id)
        .order_by(EvaluationRunCase.position)
    )
    results = list(
        await session.scalars(
            select(EvaluationCaseResult)
            .where(EvaluationCaseResult.run_id == run_id)
            .order_by(EvaluationCaseResult.repeat, EvaluationCaseResult.created_at)
        )
    )
    verdicts = await session.scalars(
        select(EvaluationVerdict)
        .where(EvaluationVerdict.result_id.in_([r.id for r in results]))
        .order_by(EvaluationVerdict.kind.desc())
    )
    by_result: dict[uuid.UUID, list[EvaluationVerdict]] = {}
    for verdict in verdicts:
        by_result.setdefault(verdict.result_id, []).append(verdict)
    return detail, [
        CaseResults(
            case,
            [
                JudgedResult(result, by_result.get(result.id, []))
                for result in results
                if result.run_case_id == case.id
            ],
        )
        for case in cases
    ]
