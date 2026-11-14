"""The Evaluation Run job: answers every case the Run copied, on each side, then judges each
answer.

Each answer is a turn of the Guardrail pipeline's ``run_turn`` with no history, the side's
effective AgentConfig and Instructions, the models they resolve to and the real retrieval
scoped to the Agent's Project, exactly as a Visitor reply runs. It creates no Conversation and no
Message, so Version KPIs, Usage rollups, the Token Budget, Admission control and Rate limits
never see a Run. The answer, its Trace and its Cost go on the case result.

The judge (the Run's judge model) then gives a ``reference_answer`` Verdict when the case has a
Reference answer, and a ``grounding`` Verdict unless the answer is the Fallback Text. A provider
error answering, or the judge failing, makes the case result an error with its reason.

Each answer commits with the Run's progress, so the Studio can poll it.
"""

import functools
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import AgentConfig, Retrieval
from app.agents.models import Agent
from app.agents.resolution import ResolvedModels, resolve_models
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.evaluation.judge import CitedExcerpt, JudgeError, JudgeRequest, judge
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunCase,
    EvaluationRunSide,
    EvaluationVerdict,
    ResultStatus,
    RunStatus,
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


def _trace(
    result_id: uuid.UUID,
    side: EvaluationRunSide,
    instructions_number: int | None,
    done: DoneEvent,
    cost_usd: Decimal | None,
    latency_ms: int,
) -> TraceOut:
    """The answer's Trace, in the shape the Studio reads a Playground answer's in."""
    cited = {chunk.chunk_id for chunk in done.cited}
    # A fallback reply or a refusal asked no model, so it names none.
    asked_none = done.refused or (done.fallback and not done.searches)
    return TraceOut(
        message_id=result_id,
        config_source=side.kind,
        agent_version_number=None,
        instructions_source=None if side.instructions_version_id is None else "version",
        instructions_version_id=side.instructions_version_id,
        instructions_version_number=instructions_number,
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
    result: EvaluationCaseResult, kind: str, passed: bool, reason: str
) -> EvaluationVerdict:
    return EvaluationVerdict(
        organisation_id=result.organisation_id,
        result_id=result.id,
        kind=kind,
        outcome=VerdictOutcome.PASS if passed else VerdictOutcome.FAIL,
        reason=reason,
    )


async def _answer_and_judge(
    session: AsyncSession,
    ports: EvaluationPorts,
    gateway: ModelGateway,
    run: EvaluationRun,
    side: EvaluationRunSide,
    resolved: ResolvedModels,
    project: Project,
    instructions_number: int | None,
    case: EvaluationRunCase,
    clock: Clock,
) -> None:
    result = EvaluationCaseResult(
        id=uuid.uuid4(),
        organisation_id=run.organisation_id,
        run_id=run.id,
        side_id=side.id,
        run_case_id=case.id,
        repeat=1,
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
        return
    latency_ms = round((clock.now() - started).total_seconds() * 1000)
    now = clock.now()
    pricing = await credential_pricing(session, resolved.chat.credential)
    usage = TokenUsage(answered.input_tokens, answered.output_tokens)
    result.cost_usd = cost(pricing, resolved.chat.model, usage, now, await price_table(session))
    result.answer = answered.answer
    result.trace = _trace(
        result.id, side, instructions_number, answered, result.cost_usd, latency_ms
    ).model_dump(mode="json")
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
        return
    await session.flush()
    session.add_all(
        _verdict(result, kind, verdict.passed, verdict.reason) for kind, verdict in verdicts.items()
    )


async def run_evaluation(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    run_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Runs a queued Run to its end. A Run that isn't queued (already picked up) is left."""
    async with sessionmaker() as session:
        run = await session.get_one(EvaluationRun, run_id, with_for_update=True)
        if run.status != RunStatus.QUEUED:
            return
        run.status = RunStatus.RUNNING
        await session.commit()
        sides = list(
            await session.scalars(
                select(EvaluationRunSide)
                .where(EvaluationRunSide.run_id == run.id)
                .order_by(EvaluationRunSide.position)
            )
        )
        cases = list(
            await session.scalars(
                select(EvaluationRunCase)
                .where(EvaluationRunCase.run_id == run.id)
                .order_by(EvaluationRunCase.position)
            )
        )
        agent = await session.get_one(Agent, run.agent_id)
        project = await session.get_one(Project, agent.project_id)
        for side in sides:
            config = AgentConfig.model_validate(side.config)
            resolved = await resolve_models(session, run.organisation_id, config)
            instructions_number = (
                None
                if side.instructions_version_id is None
                else (
                    await session.get_one(InstructionsVersion, side.instructions_version_id)
                ).number
            )
            for case in cases:
                await _answer_and_judge(
                    session,
                    ports,
                    gateway,
                    run,
                    side,
                    resolved,
                    project,
                    instructions_number,
                    case,
                    clock,
                )
                run.answers_done += 1
                await session.commit()
        run.status = RunStatus.COMPLETED
        run.finished_at = clock.now()
        await session.commit()
