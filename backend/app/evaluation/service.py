"""An Agent's Evaluation Set (its cases) and starting and reading its Evaluation Runs.

Every function takes an ``OrganisationScope`` and the Project and Agent IDs, so a case or a Run
is only found inside its own Agent of the Organisation the Member works in. An archived Agent's
set and Runs stay readable; its cases can't be changed and it starts no Run.

Starting a Run compares two sides, the first and the second, each the Draft or one of the
Agent's Versions: by default the Live Version against the Draft, or the Draft alone while the
Agent has never been Published. A Version answers with the Instructions it pins; the Draft with
the Instructions Version or Instructions Draft chosen, the Current Instructions Version by
default. Each side's models are resolved as a Visitor reply's would be
(``app.agents.resolution``), and a side that can't be is refused. Starting copies the judge (the
Evaluation Model, or else the Default Model) and the Evaluation repeats in force, snapshots each
side and every case, and leaves the Run ``queued`` for its task (``app.evaluation.job``). The
caller enqueues the task once the Run is committed. An Agent has at most one queued or running
Run; one can be cancelled, and its task stops between answers.

A case's expectations are its Expected sources (passages of the Project's Documents), its
Reference answer and Expect Fallback Text, which stands alone. Saving a case checks each Expected
source against the Knowledge Base as it is, and flags it stale when its passage can't be found
(``app.evaluation.expectations``); the case shows as having a Stale expectation.

A set holds at most ``CASES_MAX`` cases, counted under the Agent's row lock so concurrent
creates and copies can't pass it. Cases can be copied from another Agent of the Project as
independent copies. Adding a case from a Message records an Audit Event naming the case and the
Agent (never the question), and so does deleting a case; writing and editing cases are not
audited.

Reading a Run combines each case's repeats into its result on each side, and those into each
side's Evaluation score (``app.evaluation.combining``); a case that passes on the first side and
fails on the second is a Regression, the reverse an improvement. A Run with a Draft side is stale
once the Draft has a newer Draft revision. Each case in the set shows its result in the latest
finished Run that answered it.
"""

import enum
import uuid
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentVersion
from app.agents.resolution import (
    NoDefaultModelError,
    ProviderCredentialGoneError,
    ResolvedModels,
    resolve_models,
)
from app.agents.service import AgentNotFoundError, AgentWithDraft, active_agent, get_agent
from app.default_model.service import CurrentDefault
from app.documents.service import DocumentNotFoundError, get_document
from app.evaluation.combining import (
    CaseOutcome,
    Repeat,
    Score,
    SideResult,
    score,
    side_result,
)
from app.evaluation.estimate import Estimate, EstimateSide, estimate
from app.evaluation.expectations import refresh_stale
from app.evaluation.guidance import current_version
from app.evaluation.guidance_check import guidance_cost
from app.evaluation.models import (
    IN_PROGRESS,
    CaseSource,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationExpectedSource,
    EvaluationRun,
    EvaluationRunCase,
    EvaluationRunSide,
    EvaluationVerdict,
    LiveVerdict,
    RunKind,
    RunStatus,
    SideKind,
    VerdictOutcome,
)
from app.evaluation.settings import judge_model
from app.projects.instructions import project_version
from app.projects.models import InstructionsVersion, Project
from app.projects.service import active_project
from app.suggestions.reads import suggestion_in_progress
from app.tenancy.models import Organisation
from app.tenancy.repository import OrganisationScope

# An Evaluation Set's size, so a Run stays bounded in time and Cost.
CASES_MAX = 200
ADDED_FROM_MESSAGE = "agent.evaluation_case_added_from_message"
CASE_DELETED = "agent.evaluation_case_deleted"

FIRST = "first"
SECOND = "second"
REGRESSION = "regression"
IMPROVEMENT = "improvement"


class CaseNotFoundError(Exception):
    """No Evaluation Case with that ID in the Agent's set."""


class RunNotFoundError(Exception):
    """No Evaluation Run with that ID for the Agent."""


class CaseLimitError(Exception):
    """The Evaluation Set would hold more than ``CASES_MAX`` cases."""

    def __init__(self, held: int) -> None:
        super().__init__(held)
        self.held = held


class SourceAgentNotFoundError(Exception):
    """Cases are copied from another Agent of the same Project."""


class SourceCaseNotFoundError(Exception):
    """A case to copy isn't in the set of the Agent copied from."""


class NoExpectationError(Exception):
    """An Evaluation Case needs at least one expectation."""


class FallbackWithReferenceError(Exception):
    """Expect Fallback Text can't be combined with a Reference answer."""


class FallbackWithSourceError(Exception):
    """Expect Fallback Text can't be combined with an Expected source."""


class SourceDocumentNotFoundError(Exception):
    """An Expected source names no Document of the Agent's Project."""


class EmptySetError(Exception):
    """A Run needs at least one Evaluation Case."""


class VersionNotFoundError(Exception):
    """A side names no Version of the Agent."""


class SameSidesError(Exception):
    """A Run's two sides are the same."""


class RunInProgressError(Exception):
    """The Agent already has a queued or running Run."""


class SuggestionInProgressError(RunInProgressError):
    """The Agent has a Suggestion run in progress (spec 16): the Agent runs one at a time,
    Evaluation Run or Suggestion run."""


class RunFinishedError(Exception):
    """Only a queued or running Run can be cancelled."""


class VersionCredentialGoneError(ProviderCredentialGoneError):
    """A Version side names a Provider Credential that no longer exists."""

    def __init__(self, number: int) -> None:
        super().__init__(number)
        self.number = number


@dataclass(frozen=True)
class SideChoice:
    """A side to run: the Draft, or the Agent Version ``version_id`` (as it is, or as a rollout
    side)."""

    kind: SideKind
    version_id: uuid.UUID | None = None


@dataclass(frozen=True)
class SuggestionSide:
    """A Suggestion's check (spec 16): the Version it was made from against ``config``, that
    Version's AgentConfig with the suggested changes, answering with the Instructions it pins."""

    version_id: uuid.UUID
    config: AgentConfig


@dataclass(frozen=True)
class SourceFields:
    document_id: uuid.UUID
    passage: str


@dataclass(frozen=True)
class CaseFields:
    question: str
    # None or blank: no Reference answer.
    reference_answer: str | None
    expect_fallback: bool = False
    expected_sources: Sequence[SourceFields] = ()


def _checked(fields: CaseFields) -> CaseFields:
    """The fields with a blank Reference answer as none. Refused without an expectation
    (``NoExpectationError``), and for Expect Fallback Text with a Reference answer
    (``FallbackWithReferenceError``) or an Expected source (``FallbackWithSourceError``)."""
    reference = (fields.reference_answer or "").strip() or None
    sources = [SourceFields(s.document_id, s.passage.strip()) for s in fields.expected_sources]
    if fields.expect_fallback and reference is not None:
        raise FallbackWithReferenceError
    if fields.expect_fallback and sources:
        raise FallbackWithSourceError
    if reference is None and not sources and not fields.expect_fallback:
        raise NoExpectationError
    return CaseFields(fields.question, reference, fields.expect_fallback, sources)


async def _replace_sources(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    case: EvaluationCase,
    fields: Sequence[SourceFields],
) -> None:
    """Gives the case these Expected sources, in order, with their Stale flags as the Knowledge
    Base is now. Refused with ``SourceDocumentNotFoundError`` for a Document not in the
    Project."""
    names: dict[uuid.UUID, str] = {}
    for each in fields:
        try:
            names[each.document_id] = (
                await get_document(session, scope, project_id, each.document_id)
            ).name
        except DocumentNotFoundError:
            raise SourceDocumentNotFoundError from None
    await session.execute(
        delete(EvaluationExpectedSource).where(EvaluationExpectedSource.case_id == case.id)
    )
    sources = [
        EvaluationExpectedSource(
            organisation_id=case.organisation_id,
            case_id=case.id,
            position=position,
            document_id=each.document_id,
            document_name=names[each.document_id],
            passage=each.passage,
        )
        for position, each in enumerate(fields)
    ]
    await refresh_stale(session, sources)
    session.add_all(sources)


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


@dataclass(frozen=True)
class LatestResult:
    """A case's result in the latest finished Run that answered it, on that Run's last side
    (the Draft's, while the Draft runs alone)."""

    run_id: uuid.UUID
    result: SideResult


@dataclass(frozen=True)
class CaseWithResult:
    case: EvaluationCase
    # Its Expected sources, in order.
    sources: list[EvaluationExpectedSource]
    # None until a finished Run has answered the case.
    latest: LatestResult | None

    @property
    def stale(self) -> bool:
        """Whether it has a Stale expectation."""
        return any(source.stale for source in self.sources)


async def _cases(session: AsyncSession, agent_id: uuid.UUID) -> list[EvaluationCase]:
    cases = await session.scalars(
        select(EvaluationCase)
        .where(EvaluationCase.agent_id == agent_id)
        .order_by(EvaluationCase.created_at, EvaluationCase.id)
    )
    return list(cases)


async def _sources(
    session: AsyncSession, cases: Sequence[EvaluationCase]
) -> dict[uuid.UUID, list[EvaluationExpectedSource]]:
    """Each case's Expected sources, in order, by case ID."""
    sources: dict[uuid.UUID, list[EvaluationExpectedSource]] = {}
    for expected in await session.scalars(
        select(EvaluationExpectedSource)
        .where(EvaluationExpectedSource.case_id.in_([case.id for case in cases]))
        .order_by(EvaluationExpectedSource.position)
    ):
        sources.setdefault(expected.case_id, []).append(expected)
    return sources


async def _with_latest(
    session: AsyncSession, cases: Sequence[EvaluationCase]
) -> list[CaseWithResult]:
    """Each case with its result in the latest finished Run that answered it."""
    copies = await session.execute(
        select(EvaluationRunCase.case_id, EvaluationRunCase.id, EvaluationRun.id)
        .join(EvaluationRun, EvaluationRun.id == EvaluationRunCase.run_id)
        .where(
            EvaluationRunCase.case_id.in_([case.id for case in cases]),
            EvaluationRun.status.in_([RunStatus.COMPLETED, RunStatus.FAILED]),
        )
        .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id)
    )
    latest: dict[uuid.UUID | None, tuple[uuid.UUID, uuid.UUID]] = {}
    for case_id, run_case_id, run_id in copies:
        latest.setdefault(case_id, (run_case_id, run_id))
    run_ids = {run_id for _, run_id in latest.values()}
    last_sides = {
        side.run_id: side.id
        for side in await session.scalars(
            select(EvaluationRunSide)
            .where(EvaluationRunSide.run_id.in_(run_ids))
            .order_by(EvaluationRunSide.position)
        )
    }
    repeats = _by_case_and_side(await _judged(session, run_ids))
    sources = await _sources(session, cases)
    found: list[CaseWithResult] = []
    for case in cases:
        copy = latest.get(case.id)
        result = None
        if copy is not None:
            run_case_id, run_id = copy
            side = side_result(repeats.get((run_case_id, last_sides[run_id]), []))
            result = LatestResult(run_id, side)
        found.append(CaseWithResult(case, sources.get(case.id, []), result))
    return found


class ExpectationKind(enum.StrEnum):
    EXPECTED_SOURCE = "expected_source"
    REFERENCE_ANSWER = "reference_answer"
    FALLBACK = "fallback"


class LatestKind(enum.StrEnum):
    """A case's latest result as the set shows it: Unsteady over its majority outcome."""

    PASS = "pass"  # noqa: S105 (a result, not a password)
    FAIL = "fail"
    UNSTEADY = "unsteady"
    ERROR = "error"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class CaseFilter:
    # Text the question holds, letter case aside.
    search: str | None = None
    # Cases with this kind of expectation.
    kind: ExpectationKind | None = None
    # Cases with (or without) a Stale expectation.
    stale: bool | None = None
    latest: LatestKind | None = None


def _latest_kind(found: CaseWithResult) -> LatestKind:
    if found.latest is None:
        return LatestKind.NOT_RUN
    if found.latest.result.unsteady:
        return LatestKind.UNSTEADY
    return LatestKind(found.latest.result.outcome)


def _kinds(found: CaseWithResult) -> set[ExpectationKind]:
    kinds = set()
    if found.sources:
        kinds.add(ExpectationKind.EXPECTED_SOURCE)
    if found.case.reference_answer is not None:
        kinds.add(ExpectationKind.REFERENCE_ANSWER)
    if found.case.expect_fallback:
        kinds.add(ExpectationKind.FALLBACK)
    return kinds


def _matches(found: CaseWithResult, where: CaseFilter) -> bool:
    return (
        (where.search is None or where.search.casefold() in found.case.question.casefold())
        and (where.kind is None or where.kind in _kinds(found))
        and (where.stale is None or where.stale == found.stale)
        and (where.latest is None or where.latest == _latest_kind(found))
    )


async def list_cases(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    where: CaseFilter | None = None,
) -> list[CaseWithResult]:
    """The Agent's Evaluation Set, oldest case first, each with its latest result; with
    ``where``, only the cases matching every filter given."""
    found = await _agent(session, scope, project_id, agent_id, change=False)
    cases = await _with_latest(session, await _cases(session, found.agent.id))
    chosen = where or CaseFilter()
    return [case for case in cases if _matches(case, chosen)]


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
) -> CaseWithResult:
    found = await _agent(session, scope, project_id, agent_id, change=False)
    (case,) = await _with_latest(session, [await _case(session, found.agent.id, case_id)])
    return case


async def _make_room(session: AsyncSession, agent_id: uuid.UUID, adding: int) -> None:
    """Refuses with ``CaseLimitError`` when adding ``adding`` cases would take the set past
    ``CASES_MAX``. The caller holds the Agent's row lock, so concurrent adds queue behind it."""
    held = await session.scalar(
        select(func.count()).select_from(EvaluationCase).where(EvaluationCase.agent_id == agent_id)
    )
    if (held or 0) + adding > CASES_MAX:
        raise CaseLimitError(held or 0)


async def create_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    fields: CaseFields,
    *,
    source: CaseSource = CaseSource.WRITTEN,
    now: datetime,
) -> CaseWithResult:
    """Adds a case, written or added from a Message (an Audit Event naming the case and the
    Agent, never the question); refused as ``_checked``, ``_make_room`` and
    ``_replace_sources`` say."""
    checked = _checked(fields)
    found = await _agent(session, scope, project_id, agent_id, change=True)
    await _make_room(session, found.agent.id, 1)
    case = EvaluationCase(
        id=uuid.uuid4(),
        organisation_id=scope.organisation_id,
        agent_id=found.agent.id,
        question=checked.question,
        reference_answer=checked.reference_answer,
        expect_fallback=checked.expect_fallback,
        source=source,
        created_by=scope.member_id,
        created_at=now,
        updated_at=now,
    )
    session.add(case)
    await session.flush()
    await _replace_sources(session, scope, project_id, case, checked.expected_sources)
    if source == CaseSource.FROM_MESSAGE:
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=ADDED_FROM_MESSAGE,
            target=audit.AuditTarget("agent", found.agent.id),
            after={"case_id": str(case.id)},
            occurred_at=now,
        )
    await session.commit()
    (created,) = await _with_latest(session, [case])
    return created


async def copy_cases(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    from_agent_id: uuid.UUID,
    case_ids: Collection[uuid.UUID],
    *,
    now: datetime,
) -> list[CaseWithResult]:
    """Copies these cases of another Agent of the Project into the Agent's set, in their set's
    order: independent copies with their own IDs, expectations and Stale flags, and no result
    yet. Refused with ``SourceAgentNotFoundError`` for the Agent itself or one outside the
    Project, ``SourceCaseNotFoundError`` for a case not in that Agent's set, and as
    ``_make_room`` says."""
    found = await _agent(session, scope, project_id, agent_id, change=True)
    if from_agent_id == found.agent.id:
        raise SourceAgentNotFoundError
    try:
        source = await get_agent(session, scope, project_id, from_agent_id)
    except AgentNotFoundError:
        raise SourceAgentNotFoundError from None
    wanted = set(case_ids)
    originals = [case for case in await _cases(session, source.agent.id) if case.id in wanted]
    if len(originals) != len(wanted):
        raise SourceCaseNotFoundError
    await _make_room(session, found.agent.id, len(originals))
    expected = await _sources(session, originals)
    copies: list[EvaluationCase] = []
    added: list[EvaluationExpectedSource] = []
    for offset, original in enumerate(originals):
        # A microsecond apart, so the set lists them in the order they had.
        at = now + timedelta(microseconds=offset)
        copy = EvaluationCase(
            id=uuid.uuid4(),
            organisation_id=scope.organisation_id,
            agent_id=found.agent.id,
            question=original.question,
            reference_answer=original.reference_answer,
            expect_fallback=original.expect_fallback,
            source=original.source,
            created_by=scope.member_id,
            created_at=at,
            updated_at=at,
        )
        copies.append(copy)
        added.extend(
            EvaluationExpectedSource(
                organisation_id=scope.organisation_id,
                case_id=copy.id,
                position=each.position,
                document_id=each.document_id,
                document_name=each.document_name,
                passage=each.passage,
            )
            for each in expected.get(original.id, [])
        )
    session.add_all(copies)
    await session.flush()
    await refresh_stale(session, added)
    session.add_all(added)
    await session.commit()
    return await _with_latest(session, copies)


async def update_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
    fields: CaseFields,
    *,
    now: datetime,
) -> CaseWithResult:
    """Replaces the case's question and expectations. Past Runs keep their copies, and its
    latest result stays until a Run answers it again."""
    checked = _checked(fields)
    found = await _agent(session, scope, project_id, agent_id, change=True)
    case = await _case(session, found.agent.id, case_id)
    case.question = checked.question
    case.reference_answer = checked.reference_answer
    case.expect_fallback = checked.expect_fallback
    case.updated_at = now
    await _replace_sources(session, scope, project_id, case, checked.expected_sources)
    await session.commit()
    (updated,) = await _with_latest(session, [case])
    return updated


async def delete_case(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    case_id: uuid.UUID,
    *,
    now: datetime,
) -> None:
    """Deletes the case, an Audit Event. Past Runs keep their copies of it."""
    found = await _agent(session, scope, project_id, agent_id, change=True)
    case = await _case(session, found.agent.id, case_id)
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=CASE_DELETED,
        target=audit.AuditTarget("agent", found.agent.id),
        before={"case_id": str(case.id), "source": case.source},
        occurred_at=now,
    )
    await session.delete(case)
    await session.commit()


@dataclass(frozen=True)
class DependentAgent:
    agent_id: uuid.UUID
    name: str
    # How many of its cases hold an Expected source in the Document.
    case_count: int


@dataclass(frozen=True)
class Dependents:
    """Who holds an Expected source in a Document: the Expected source warning's facts."""

    # By Agent name.
    agents: list[DependentAgent]
    # Every distinct passage of the Document used as an Expected source, in code-point order.
    passages: list[str]


async def expected_source_dependents(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, document_id: uuid.UUID
) -> Dependents:
    """The Agents and case counts holding an Expected source in the Document, and its passages,
    for the Studio to warn before the Document is deleted or a new Edition uploaded."""
    document = await get_document(session, scope, project_id, document_id)
    held = EvaluationExpectedSource.document_id == document.id
    rows = await session.execute(
        select(Agent.id, Agent.name, func.count(func.distinct(EvaluationCase.id)))
        .join(EvaluationCase, EvaluationCase.agent_id == Agent.id)
        .join(EvaluationExpectedSource, EvaluationExpectedSource.case_id == EvaluationCase.id)
        .where(held)
        .group_by(Agent.id, Agent.name)
        .order_by(Agent.name, Agent.id)
    )
    passages = await session.scalars(select(EvaluationExpectedSource.passage).where(held))
    return Dependents(
        [DependentAgent(agent_id, name, count) for agent_id, name, count in rows],
        sorted(set(passages)),
    )


@dataclass(frozen=True)
class _Side:
    """A side resolved to what it runs: its configuration, models and Instructions."""

    choice: SideChoice
    version: AgentVersion | None
    resolved: ResolvedModels
    instructions: InstructionsVersion | None
    instructions_draft: bool
    instructions_text: str


async def _version_side(
    session: AsyncSession, scope: OrganisationScope, agent_id: uuid.UUID, choice: SideChoice
) -> _Side:
    version = (
        None
        if choice.version_id is None
        else await session.scalar(
            select(AgentVersion).where(
                AgentVersion.id == choice.version_id, AgentVersion.agent_id == agent_id
            )
        )
    )
    if version is None:
        raise VersionNotFoundError
    try:
        resolved = await resolve_models(
            session, scope.organisation_id, AgentConfig.model_validate(version.config)
        )
    except ProviderCredentialGoneError:
        raise VersionCredentialGoneError(version.number) from None
    pinned = (
        None
        if version.instructions_version_id is None
        else await session.get_one(InstructionsVersion, version.instructions_version_id)
    )
    return _Side(
        choice, version, resolved, pinned, False, "" if pinned is None else pinned.markdown
    )


async def _draft_instructions(
    session: AsyncSession,
    project: Project,
    instructions_version_id: uuid.UUID | None,
    instructions_draft: bool,
) -> tuple[InstructionsVersion | None, bool, str]:
    """The Instructions the Draft answers with: the chosen Instructions Version (refused with
    ``InstructionsVersionNotFoundError`` if it isn't the Project's), else the Instructions Draft
    when chosen, else the Current Instructions Version (none while the Project has none)."""
    if instructions_version_id is not None:
        chosen = await project_version(session, project, instructions_version_id)
        return chosen, False, chosen.markdown
    if instructions_draft:
        return None, True, project.instructions
    if project.current_instructions_version_id is None:
        return None, False, ""
    current = await session.get_one(InstructionsVersion, project.current_instructions_version_id)
    return current, False, current.markdown


async def run_in_progress(session: AsyncSession, agent_id: uuid.UUID) -> bool:
    """Whether the Agent has a queued or running Run."""
    found = await session.scalar(
        select(EvaluationRun.id).where(
            EvaluationRun.agent_id == agent_id, EvaluationRun.status.in_(IN_PROGRESS)
        )
    )
    return found is not None


@dataclass(frozen=True)
class Plan:
    """What a Run of the Agent's set would answer and judge with, and what it would cost."""

    agent: AgentWithDraft
    cases: list[EvaluationCase]
    sides: list[_Side]
    judge: CurrentDefault
    repeats: int
    estimate: Estimate


async def plan_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    sides: Sequence[SideChoice] | None,
    instructions_version_id: uuid.UUID | None,
    instructions_draft: bool,
    starting: bool,
    now: datetime,
    rollout: InstructionsVersion | None = None,
    suggestion: SuggestionSide | None = None,
) -> Plan:
    """Resolves a Run's sides, judge and repeats, refusing as ``start_run`` says. When
    ``starting``, the Agent's row is locked and a Run or Suggestion run in progress is refused.
    With ``rollout``, the sides are the Live Version against its rollout side answering with
    those Instructions. With ``suggestion``, they are its Version against the suggestion side,
    and the Suggestion run in progress is the one checking."""
    project = await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id, lock=starting)
    # A Suggestion's check is a Run of its Suggestion run in progress: Evaluate is refused as
    # that Suggestion run's, not as a Run's.
    if starting and suggestion is None and await suggestion_in_progress(session, found.agent.id):
        raise SuggestionInProgressError
    if starting and await run_in_progress(session, found.agent.id):
        raise RunInProgressError
    cases = await _cases(session, found.agent.id)
    if not cases:
        raise EmptySetError
    live = found.agent.live_version_id
    if rollout is not None:
        sides = [SideChoice(SideKind.VERSION, live), SideChoice(SideKind.ROLLOUT, live)]
    elif suggestion is not None:
        sides = [
            SideChoice(SideKind.VERSION, suggestion.version_id),
            SideChoice(SideKind.SUGGESTION, suggestion.version_id),
        ]
    elif sides is None:
        sides = [SideChoice(SideKind.DRAFT)]
        if live is not None:
            sides = [SideChoice(SideKind.VERSION, live), *sides]
    keys = [(c.kind, c.version_id if c.kind == SideKind.VERSION else None) for c in sides]
    if len(set(keys)) < len(keys):
        raise SameSidesError
    draft_instructions = await _draft_instructions(
        session, project, instructions_version_id, instructions_draft
    )
    resolved_sides: list[_Side] = []
    for choice in sides:
        if choice.kind != SideKind.DRAFT:
            side = await _version_side(session, scope, found.agent.id, choice)
            if rollout is not None and choice.kind == SideKind.ROLLOUT:
                side = replace(side, instructions=rollout, instructions_text=rollout.markdown)
            if suggestion is not None and choice.kind == SideKind.SUGGESTION:
                resolved = await resolve_models(session, scope.organisation_id, suggestion.config)
                side = replace(side, resolved=resolved)
            resolved_sides.append(side)
            continue
        resolved = await resolve_models(session, scope.organisation_id, found.draft)
        resolved_sides.append(_Side(choice, None, resolved, *draft_instructions))
    judge = await judge_model(session, scope.organisation_id)
    if judge is None:
        raise NoDefaultModelError
    repeats = (await session.get_one(Organisation, scope.organisation_id)).evaluation_repeats
    estimated = await estimate(
        session,
        [
            EstimateSide(
                found.agent.id,
                None if side.version is None else side.version.id,
                side.resolved.chat.credential,
                side.resolved.chat.model,
            )
            for side in resolved_sides
        ],
        judge.credential,
        judge.model,
        cases=len(cases),
        repeats=repeats,
        now=now,
    )
    return Plan(found, cases, resolved_sides, judge, repeats, estimated)


async def estimate_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    sides: Sequence[SideChoice] | None = None,
    instructions_version_id: uuid.UUID | None = None,
    instructions_draft: bool = False,
    now: datetime,
) -> Estimate:
    """The estimated Cost of starting a Run with these choices now, refused as ``start_run``
    would be (except while a Run is in progress)."""
    plan = await plan_run(
        session,
        scope,
        project_id,
        agent_id,
        sides=sides,
        instructions_version_id=instructions_version_id,
        instructions_draft=instructions_draft,
        starting=False,
        now=now,
    )
    return plan.estimate


async def start_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    sides: Sequence[SideChoice] | None = None,
    instructions_version_id: uuid.UUID | None = None,
    instructions_draft: bool = False,
    now: datetime,
) -> EvaluationRun:
    """A queued Run of ``sides`` (one or two; by default the Live Version against the Draft, or
    the Draft alone while the Agent isn't live), the Draft answering with the chosen
    Instructions, each side answering each case as many times as the Evaluation repeats. Its
    estimated Cost is stored on it.

    Refused for an archived Agent, while it has a Run in progress (``RunInProgressError``), for
    an empty set (``EmptySetError``), for a side that isn't the Agent's
    (``VersionNotFoundError``) or two sides that are the same (``SameSidesError``), for chosen
    Instructions that aren't the Project's (``InstructionsVersionNotFoundError``), for a side
    that can't be resolved (``NoDefaultModelError``, ``ProviderCredentialGoneError``, or
    ``VersionCredentialGoneError`` naming the Version), and for an Organisation with neither an
    Evaluation Model nor a Default Model to judge."""
    plan = await plan_run(
        session,
        scope,
        project_id,
        agent_id,
        sides=sides,
        instructions_version_id=instructions_version_id,
        instructions_draft=instructions_draft,
        starting=True,
        now=now,
    )
    run = await add_run(session, scope, plan, RunKind.AGENT, now=now, started_by=scope.member_id)
    await session.commit()
    return run


async def add_run(
    session: AsyncSession,
    scope: OrganisationScope,
    plan: Plan,
    kind: RunKind,
    *,
    now: datetime,
    started_by: uuid.UUID | None,
) -> EvaluationRun:
    """Adds the queued Run ``plan`` describes, started by the Member ``started_by``, with its
    sides and its copy of every case, for the caller to commit."""
    found, cases, resolved_sides, judge, repeats = (
        plan.agent,
        plan.cases,
        plan.sides,
        plan.judge,
        plan.repeats,
    )
    sources = await _sources(session, cases)
    run = EvaluationRun(
        organisation_id=scope.organisation_id,
        agent_id=found.agent.id,
        status=RunStatus.QUEUED,
        kind=kind,
        started_by=started_by,
        judge_credential_id=judge.credential.id,
        judge_provider=judge.credential.provider,
        judge_model=judge.model,
        judging_guidance_version=await current_version(session, scope.organisation_id),
        repeats=repeats,
        answers_done=0,
        answers_total=len(cases) * repeats * len(resolved_sides),
        estimated_cost_usd=plan.estimate.total_usd,
        created_at=now,
    )
    session.add(run)
    await session.flush()
    session.add_all(
        EvaluationRunSide(
            organisation_id=scope.organisation_id,
            run_id=run.id,
            position=position,
            kind=side.choice.kind,
            agent_version_id=None if side.version is None else side.version.id,
            draft_revision=None if side.version is not None else found.draft_revision,
            instructions_version_id=None if side.instructions is None else side.instructions.id,
            instructions_draft=side.instructions_draft,
            instructions=side.instructions_text,
            config=side.resolved.config.model_dump(mode="json"),
            chat_provider=side.resolved.chat.credential.provider,
            chat_model=side.resolved.chat.model,
            automatic_fallback=side.resolved.automatic_fallback,
        )
        for position, side in zip((FIRST, SECOND), resolved_sides, strict=False)
    )
    session.add_all(
        EvaluationRunCase(
            organisation_id=scope.organisation_id,
            run_id=run.id,
            case_id=case.id,
            position=position,
            question=case.question,
            reference_answer=case.reference_answer,
            expect_fallback=case.expect_fallback,
            expected_sources=[
                {
                    "source_id": str(expected.id),
                    "document_id": None
                    if expected.document_id is None
                    else str(expected.document_id),
                    "document_name": expected.document_name,
                    "passage": expected.passage,
                }
                for expected in sources.get(case.id, [])
            ],
        )
        for position, case in enumerate(cases)
    )
    await session.flush()
    return run


async def cancel_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    now: datetime,
) -> None:
    """Cancels a queued or running Run (``RunFinishedError`` otherwise). Its task stops before
    its next answer; what it answered and spent so far is kept."""
    found = await _agent(session, scope, project_id, agent_id, change=False)
    run = await session.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.id == run_id, EvaluationRun.agent_id == found.agent.id)
        .with_for_update()
    )
    if run is None:
        raise RunNotFoundError
    if run.status not in IN_PROGRESS:
        raise RunFinishedError
    run.status = RunStatus.CANCELLED
    run.finished_at = now
    await session.commit()


async def evaluation_cost(
    session: AsyncSession, organisation_id: uuid.UUID, start: datetime, before: datetime
) -> dict[uuid.UUID, Decimal]:
    """What each Agent's Evaluation Runs (answers and judging), Live Verdicts and guidance checks'
    re-judging cost from ``start`` until ``before``, by when each answer was given and each Live
    Verdict or target judged, at the prices frozen then. Organisation cost reads it; it never
    counts in Version KPIs or the Token Budget."""
    spent = func.coalesce(EvaluationCaseResult.cost_usd, 0) + func.coalesce(
        EvaluationCaseResult.judge_cost_usd, 0
    )
    rows = await session.execute(
        select(EvaluationRun.agent_id, func.sum(spent))
        .join(EvaluationRun, EvaluationRun.id == EvaluationCaseResult.run_id)
        .where(
            EvaluationCaseResult.organisation_id == organisation_id,
            EvaluationCaseResult.created_at >= start,
            EvaluationCaseResult.created_at < before,
        )
        .group_by(EvaluationRun.agent_id)
    )
    cost = {agent_id: Decimal(total) for agent_id, total in rows}
    live = await session.execute(
        select(LiveVerdict.agent_id, func.sum(LiveVerdict.cost_usd))
        .where(
            LiveVerdict.organisation_id == organisation_id,
            LiveVerdict.cost_usd.is_not(None),
            LiveVerdict.judged_at >= start,
            LiveVerdict.judged_at < before,
        )
        .group_by(LiveVerdict.agent_id)
    )
    for agent_id, total in live:
        # Only Live Verdicts with a Cost are summed.
        cost[agent_id] = cost.get(agent_id, Decimal(0)) + cast(Decimal, total)
    # Guidance checks re-judge the Agent's targets (spec 19): counted as evaluation too.
    for agent_id, total in (await guidance_cost(session, organisation_id, start, before)).items():
        cost[agent_id] = cost.get(agent_id, Decimal(0)) + total
    return cost


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
class JudgedResult:
    result: EvaluationCaseResult
    verdicts: list[EvaluationVerdict]


async def _judged(session: AsyncSession, run_ids: Iterable[uuid.UUID]) -> list[JudgedResult]:
    """The Runs' answers with their Verdicts, repeat by repeat."""
    results = list(
        await session.scalars(
            select(EvaluationCaseResult)
            .where(EvaluationCaseResult.run_id.in_(list(run_ids)))
            .order_by(EvaluationCaseResult.repeat, EvaluationCaseResult.created_at)
        )
    )
    verdicts = await session.scalars(
        select(EvaluationVerdict)
        .where(EvaluationVerdict.result_id.in_([r.id for r in results]))
        .order_by(EvaluationVerdict.position, EvaluationVerdict.kind.desc())
    )
    by_result: dict[uuid.UUID, list[EvaluationVerdict]] = {}
    for verdict in verdicts:
        by_result.setdefault(verdict.result_id, []).append(verdict)
    return [JudgedResult(result, by_result.get(result.id, [])) for result in results]


def _by_case_and_side(
    judged: Iterable[JudgedResult],
) -> dict[tuple[uuid.UUID, uuid.UUID], list[Repeat]]:
    """The repeats of each copied case on each side."""
    repeats: dict[tuple[uuid.UUID, uuid.UUID], list[Repeat]] = {}
    for found in judged:
        key = (found.result.run_case_id, found.result.side_id)
        repeats.setdefault(key, []).append(Repeat(found.result, found.verdicts))
    return repeats


@dataclass(frozen=True)
class RunDetail:
    run: EvaluationRun
    sides: list[EvaluationRunSide]
    # The Instructions Versions' and the Agent Versions' numbers, by ID.
    instructions_numbers: dict[uuid.UUID, int]
    version_numbers: dict[uuid.UUID, int]
    # Each side's Evaluation score, by side ID, from the cases answered so far.
    scores: dict[uuid.UUID, Score]
    # Whether it has a Draft side and the Draft has a newer Draft revision since.
    stale: bool
    # Its actual Cost so far, in US dollars, at the prices frozen as each answer and judgement
    # ran: answering and judging (a call with no known price adds nothing).
    answers_cost_usd: Decimal
    judging_cost_usd: Decimal


async def _run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
) -> RunDetail:
    """The Run, with no scores yet."""
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
    instructions = {s.instructions_version_id for s in sides if s.instructions_version_id}
    numbers = await session.execute(
        select(InstructionsVersion.id, InstructionsVersion.number).where(
            InstructionsVersion.id.in_(instructions)
        )
    )
    versions = await session.execute(
        select(AgentVersion.id, AgentVersion.number).where(
            AgentVersion.id.in_({s.agent_version_id for s in sides if s.agent_version_id})
        )
    )
    stale = any(
        side.kind == SideKind.DRAFT and side.draft_revision != found.draft_revision
        for side in sides
    )
    answers, judging = (
        await session.execute(
            select(
                func.sum(EvaluationCaseResult.cost_usd),
                func.sum(EvaluationCaseResult.judge_cost_usd),
            ).where(EvaluationCaseResult.run_id == run.id)
        )
    ).one()
    return RunDetail(
        run,
        sides,
        {row.id: row.number for row in numbers},
        {row.id: row.number for row in versions},
        {},
        stale,
        answers or Decimal(0),
        judging or Decimal(0),
    )


def _scored(
    detail: RunDetail, repeats: dict[tuple[uuid.UUID, uuid.UUID], list[Repeat]]
) -> RunDetail:
    scores = {
        side.id: score(
            side_result(found) for (_, side_id), found in repeats.items() if side_id == side.id
        )
        for side in detail.sides
    }
    return replace(detail, scores=scores)


async def get_run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
) -> RunDetail:
    detail = await _run(session, scope, project_id, agent_id, run_id)
    return _scored(detail, _by_case_and_side(await _judged(session, [run_id])))


@dataclass(frozen=True)
class CaseResults:
    """A case as the Run copied it, with each side's answers and its result on each side."""

    case: EvaluationRunCase
    results: list[JudgedResult]
    # By side ID; a side that hasn't answered the case yet has none.
    sides: dict[uuid.UUID, SideResult]
    # ``regression`` when it passes on the first side and fails on the second,
    # ``improvement`` for the reverse; None otherwise.
    change: str | None

    @property
    def unsteady(self) -> bool:
        """Whether its repeats disagreed on either side."""
        return any(result.unsteady for result in self.sides.values())

    @property
    def stale_expectation(self) -> bool:
        """Whether an answer skipped a Stale expectation."""
        return any(
            verdict.outcome == VerdictOutcome.STALE
            for judged in self.results
            for verdict in judged.verdicts
        )


def _change(first: SideResult | None, second: SideResult | None) -> str | None:
    outcomes = (
        None if first is None else first.outcome,
        None if second is None else second.outcome,
    )
    if outcomes == (CaseOutcome.PASS, CaseOutcome.FAIL):
        return REGRESSION
    if outcomes == (CaseOutcome.FAIL, CaseOutcome.PASS):
        return IMPROVEMENT
    return None


_ORDER = {REGRESSION: 0, IMPROVEMENT: 1, None: 2}


async def run_results(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
) -> tuple[RunDetail, list[CaseResults]]:
    """The Run's cases, Regressions first, then improvements, then the rest, each in set order,
    with its answers, their Verdicts, and its result on each side."""
    detail = await _run(session, scope, project_id, agent_id, run_id)
    cases = await session.scalars(
        select(EvaluationRunCase)
        .where(EvaluationRunCase.run_id == run_id)
        .order_by(EvaluationRunCase.position)
    )
    judged = await _judged(session, [run_id])
    repeats = _by_case_and_side(judged)
    found: list[CaseResults] = []
    for case in cases:
        results = {
            side.position: side_result(repeats[(case.id, side.id)])
            for side in detail.sides
            if (case.id, side.id) in repeats
        }
        found.append(
            CaseResults(
                case,
                [each for each in judged if each.result.run_case_id == case.id],
                {
                    side.id: results[side.position]
                    for side in detail.sides
                    if side.position in results
                },
                _change(results.get(FIRST), results.get(SECOND)),
            )
        )
    return _scored(detail, repeats), sorted(found, key=lambda each: _ORDER[each.change])
