"""The Evaluation Run job: answers every case the Run copied, on each side, as many times as
the Run's repeats, and judges each answer once. The sides take turns case by case, so both
answer each case at the same moment, against the same Knowledge Base.

Each answer is a turn of the Guardrail pipeline's ``run_turn`` with no history, the side's
effective AgentConfig and Instructions, the models they resolve to and the real retrieval
scoped to the Agent's Project, exactly as a Visitor reply runs. It creates no Conversation and no
Message, so Version KPIs, Usage rollups, the Token Budget, Admission control and Rate limits
never see a Run. The answer, its Trace and its Cost go on the case result.

Each repeat is a fresh answer. Each Expected source gets an ``expected_source`` Verdict and Expect
Fallback Text a ``fallback`` one, checked without a model (``app.evaluation.expectations``); a
Stale expectation's Verdict is ``stale``, and the Evaluation Set's Stale flags follow what the Run
found. The judge (the Run's judge model) then gives a ``reference_answer`` Verdict when the case
has a Reference answer, and a ``grounding`` Verdict unless the answer is the Fallback Text; with
neither to give, it isn't asked. A provider error answering, or the judge failing, makes
the case result an error with its reason; a Guardrail block is an answer, and is judged like one.

Each answer commits with the Run's progress, so the Studio can poll it. A Run cancelled meanwhile
stops before its next answer and keeps what it answered and spent. A Run where every answer
errored (so every case is an Error) ends ``failed``, with the most common error as its message.
"""

import functools
import uuid
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import AgentConfig, Retrieval
from app.agents.models import Agent, AgentVersion
from app.agents.resolution import ResolvedModels, resolve_models
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.documents.service import current_chunks
from app.evaluation.expectations import Check, check_expected_source, check_fallback
from app.evaluation.judge import (
    CitedExcerpt,
    Judged,
    JudgedVerdict,
    JudgeError,
    JudgeRequest,
    judge,
)
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationExpectedSource,
    EvaluationRun,
    EvaluationRunCase,
    EvaluationRunSide,
    EvaluationVerdict,
    ResultStatus,
    RunStatus,
    VerdictKind,
    VerdictOutcome,
)
from app.evaluation.ports import EvaluationPorts
from app.gateway.gateway import ModelGateway
from app.playground.api import GuardrailOutcomeOut, SearchOut, TracedChunkOut, TraceOut
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import TokenUsage, cost
from app.projects.models import InstructionsVersion, Project
from app.retrieval.service import Candidate, Excluded, RetrievalResult, retrieve
from app.runtime.errors import PROVIDER_ERRORS, ErrorEvent, provider_error
from app.runtime.runtime import DoneEvent


def _chunk(found: Candidate | Excluded, cited: set[uuid.UUID]) -> TracedChunkOut:
    return TracedChunkOut(
        chunk_id=found.chunk_id,
        document_id=found.document_id,
        document_name=found.document_name,
        document_deleted=False,
        text=found.text,
        score=found.score,
        relevance=found.relevance,
        rank=found.rank if isinstance(found, Candidate) else None,
        cited=isinstance(found, Candidate) and found.chunk_id in cited,
        excluded_reason=None if isinstance(found, Candidate) else found.reason,
    )


@dataclass(frozen=True)
class _Side:
    """A side as the job answers with it."""

    side: EvaluationRunSide
    resolved: ResolvedModels
    instructions_number: int | None
    version_number: int | None


def _instructions_source(side: EvaluationRunSide) -> str | None:
    if side.instructions_draft:
        return "draft"
    return None if side.instructions_version_id is None else "version"


def _trace(
    result_id: uuid.UUID,
    answering: _Side,
    done: DoneEvent,
    cost_usd: Decimal | None,
    latency_ms: int,
) -> TraceOut:
    """The answer's Trace, in the shape the Studio reads a Playground answer's in."""
    side = answering.side
    cited = {chunk.chunk_id for chunk in done.cited}
    # A fallback reply or a refusal asked no model, so it names none.
    asked_none = done.refused or (done.fallback and not done.searches)
    return TraceOut(
        message_id=result_id,
        config_source=side.kind,
        agent_version_number=answering.version_number,
        instructions_source=_instructions_source(side),
        instructions_version_id=side.instructions_version_id,
        instructions_version_number=answering.instructions_number,
        agent_version_id=side.agent_version_id,
        model_provider=None if asked_none else side.chat_provider,
        model_name=None if asked_none else side.chat_model,
        input_tokens=done.input_tokens,
        output_tokens=done.output_tokens,
        cost_usd=cost_usd,
        first_token_ms=latency_ms,
        latency_ms=latency_ms,
        fallback=done.fallback,
        chunks=[]
        if done.searches
        else [
            *(_chunk(c, cited) for c in done.retrieved),
            *(_chunk(c, cited) for c in done.excluded),
        ],
        search_count=done.search_count,
        searches=[
            SearchOut(
                order=search.order,
                query=search.query,
                latency_ms=search.latency_ms,
                limit_refused=search.limit_refused,
                chunks=[
                    *(_chunk(c, cited) for c in search.candidates),
                    *(_chunk(c, cited) for c in search.excluded),
                ],
            )
            for search in done.searches
        ],
        automatic_fallback=side.automatic_fallback,
        guardrail_outcomes=[
            GuardrailOutcomeOut.model_validate(o.as_dict()) for o in done.guardrail_outcomes
        ],
    )


async def _answer(
    session: AsyncSession,
    ports: EvaluationPorts,
    gateway: ModelGateway,
    project: Project,
    resolved: ResolvedModels,
    instructions: str,
    question: str,
) -> DoneEvent | ErrorEvent:
    """One answer to ``question``, as a Visitor reply with no history would be given."""
    chosen = resolved.chat
    try:
        model = gateway.chat_model(chosen.credential, chosen.model)
        reranker = (
            None
            if resolved.reranker is None
            else gateway.reranker(resolved.reranker.credential, resolved.reranker.model)
        )
    except PROVIDER_ERRORS as error:
        return provider_error(error, chosen.model)
    judging = resolved.classifier
    llm_classifier = (
        None
        if judging is None
        else ports.guardrails.llm_classifier(
            functools.partial(gateway.chat_model, judging.credential, judging.model),
            judging.model,
        )
    )

    async def retrieve_in_project(query: str, settings: Retrieval) -> RetrievalResult:
        return await retrieve(session, project, query, settings, ports.embedders, reranker=reranker)

    ended = [
        event
        async for event in ports.guardrails.run_turn(
            [],
            resolved.config,
            instructions,
            question,
            model=model,
            retrieve=retrieve_in_project,
            llm_classifier=llm_classifier,
        )
        if isinstance(event, DoneEvent | ErrorEvent)
    ]
    return ended[-1]


def _verdict(
    result: EvaluationCaseResult, position: int, kind: str, outcome: VerdictOutcome, reason: str
) -> EvaluationVerdict:
    return EvaluationVerdict(
        organisation_id=result.organisation_id,
        result_id=result.id,
        kind=kind,
        position=position,
        outcome=outcome,
        reason=reason,
    )


async def _checks(
    session: AsyncSession,
    case: EvaluationRunCase,
    answered: DoneEvent,
    config: AgentConfig,
) -> list[tuple[VerdictKind, Check]]:
    """The checks that need no model: each Expected source, in order, then Expect Fallback Text.
    Each Expected source's Stale flag in the Evaluation Set is set to what was found."""
    copied = case.expected_sources
    current = await current_chunks(
        session, [uuid.UUID(c["document_id"]) for c in copied if c["document_id"] is not None]
    )
    cited = {chunk.chunk_id for chunk in answered.cited}
    retrieved = {chunk.chunk_id for chunk in answered.retrieved}
    checks: list[tuple[VerdictKind, Check]] = []
    for each in copied:
        document_id = each["document_id"]
        check = check_expected_source(
            each["document_name"],
            each["passage"],
            None if document_id is None else current.get(uuid.UUID(document_id)),
            cited=cited,
            retrieved=retrieved,
        )
        await session.execute(
            update(EvaluationExpectedSource)
            .where(EvaluationExpectedSource.id == uuid.UUID(each["source_id"]))
            .values(stale=check.stale_reason is not None, stale_reason=check.stale_reason)
        )
        checks.append((VerdictKind.EXPECTED_SOURCE, check))
    if case.expect_fallback:
        check = check_fallback(
            answered.answer, fallback=answered.fallback, refused=answered.refused, config=config
        )
        checks.append((VerdictKind.FALLBACK, check))
    return checks


async def _answer_and_judge(
    session: AsyncSession,
    ports: EvaluationPorts,
    gateway: ModelGateway,
    run: EvaluationRun,
    answering: _Side,
    project: Project,
    case: EvaluationRunCase,
    repeat: int,
    clock: Clock,
) -> EvaluationCaseResult:
    """Answers the case once more and judges the answer; the case result, answered or error."""
    side, resolved = answering.side, answering.resolved
    result = EvaluationCaseResult(
        id=uuid.uuid4(),
        organisation_id=run.organisation_id,
        run_id=run.id,
        side_id=side.id,
        run_case_id=case.id,
        repeat=repeat,
        status=ResultStatus.ANSWERED,
        created_at=clock.now(),
    )
    started = clock.now()
    answered = await _answer(
        session, ports, gateway, project, resolved, side.instructions, case.question
    )
    session.add(result)
    if isinstance(answered, ErrorEvent):
        result.status = ResultStatus.ERROR
        result.error_reason = answered.message
        return result
    latency_ms = round((clock.now() - started).total_seconds() * 1000)
    now = clock.now()
    pricing = await credential_pricing(session, resolved.chat.credential)
    usage = TokenUsage(answered.input_tokens, answered.output_tokens)
    result.cost_usd = cost(pricing, resolved.chat.model, usage, now, await price_table(session))
    result.answer = answered.answer
    result.trace = _trace(result.id, answering, answered, result.cost_usd, latency_ms).model_dump(
        mode="json"
    )
    request = JudgeRequest(
        question=case.question,
        answer=answered.answer,
        cited=[
            CitedExcerpt(f"C{chunk.rank}", chunk.document_name, chunk.text)
            for chunk in answered.cited
        ],
        reference_answer=case.reference_answer,
        grounding=not answered.fallback,
    )
    checks = await _checks(session, case, answered, resolved.config)
    verdicts: dict[Judged, JudgedVerdict] = {}
    if request.asked:
        credential = await session.get_one(ProviderCredential, run.judge_credential_id)
        try:
            verdicts = await judge(
                functools.partial(gateway.chat_model, credential, run.judge_model),
                run.judge_model,
                request,
                timeout_s=ports.judge_timeout_s,
            )
        except JudgeError as error:
            result.status = ResultStatus.ERROR
            result.error_reason = error.message
            return result
    await session.flush()
    judged = [
        (kind, VerdictOutcome.PASS if verdict.passed else VerdictOutcome.FAIL, verdict.reason)
        for kind, verdict in verdicts.items()
    ]
    session.add_all(
        _verdict(result, position, kind, outcome, reason)
        for position, (kind, outcome, reason) in enumerate(
            [*((kind, check.outcome, check.reason) for kind, check in checks), *judged]
        )
    )
    return result


async def _sides(session: AsyncSession, run: EvaluationRun) -> list[_Side]:
    sides = await session.scalars(
        select(EvaluationRunSide)
        .where(EvaluationRunSide.run_id == run.id)
        .order_by(EvaluationRunSide.position)
    )
    found: list[_Side] = []
    for side in sides:
        config = AgentConfig.model_validate(side.config)
        instructions = (
            None
            if side.instructions_version_id is None
            else await session.get_one(InstructionsVersion, side.instructions_version_id)
        )
        version = (
            None
            if side.agent_version_id is None
            else await session.get_one(AgentVersion, side.agent_version_id)
        )
        found.append(
            _Side(
                side,
                await resolve_models(session, run.organisation_id, config),
                None if instructions is None else instructions.number,
                None if version is None else version.number,
            )
        )
    return found


async def run_evaluation(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    run_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Runs a queued Run to its end, or until it is cancelled. A Run that isn't queued (already
    picked up, or cancelled before it was) is left."""
    async with sessionmaker() as session:
        run = await session.get_one(EvaluationRun, run_id, with_for_update=True)
        if run.status != RunStatus.QUEUED:
            return
        run.status = RunStatus.RUNNING
        await session.commit()
        sides = await _sides(session, run)
        cases = list(
            await session.scalars(
                select(EvaluationRunCase)
                .where(EvaluationRunCase.run_id == run.id)
                .order_by(EvaluationRunCase.position)
            )
        )
        agent = await session.get_one(Agent, run.agent_id)
        project = await session.get_one(Project, agent.project_id)
        # Each error reason, by how many answers it stopped.
        errors: Counter[str | None] = Counter()
        for case in cases:
            for repeat in range(1, run.repeats + 1):
                for side in sides:
                    # Cancelled meanwhile: stop before the next answer.
                    await session.refresh(run, ["status"])
                    if run.status == RunStatus.CANCELLED:
                        return
                    result = await _answer_and_judge(
                        session, ports, gateway, run, side, project, case, repeat, clock
                    )
                    errors[result.error_reason] += result.status == ResultStatus.ERROR
                    run.answers_done += 1
                    await session.commit()
        # Cancelled during the last answer: it stays cancelled.
        await session.refresh(run, ["status"], with_for_update=True)
        if run.status == RunStatus.CANCELLED:
            return
        if errors.total() == run.answers_done:
            run.status = RunStatus.FAILED
            run.error_message = errors.most_common(1)[0][0]
        else:
            run.status = RunStatus.COMPLETED
        run.finished_at = clock.now()
        await session.commit()
