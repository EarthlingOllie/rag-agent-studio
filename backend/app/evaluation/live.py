"""Live Verdicts (spec 15): choosing Visitor replies by the Agent's Live sample rate, and judging a
chosen one in the background with the Evaluation Model.

Choosing happens after a Visitor reply is stored and sent, so it never delays or changes it. A
reply is a candidate unless it is a Guardrail block or the Fallback Text, and only while its
Agent isn't archived; a draw from the one module-level random source chooses it with the
Agent's Live sample rate. The draw is seeded from ``Settings.live_sample_seed``, which tests set, so
a sampled subset is stable. A chosen reply gets a ``pending`` Live Verdict, committed before its
task is sent. The Playground never calls this: only the widget's replies are sampled.

The task judges the question, the reply and the Chunks the reply was given (cited and not, each
in its own data block) through the Model gateway with the Evaluation Model (or the Default Model,
as for Evaluation Runs): spec 14's judge, asked for ``grounding`` and ``answers_question`` in one
structured-output call at temperature 0. The system prompt and Project Instructions are never
sent. The reply passes when both checks pass. A judge error or timeout makes the Live Verdict an
``error`` with its reason; there is no retry, so an outage doesn't multiply spend. The judge's
Cost is frozen with the cost function and Price table in force when it is judged.
"""

import functools
import random
import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.models import Agent
from app.conversations.models import Message
from app.conversations.service import traced_chunks
from app.core.clock import Clock
from app.evaluation.from_message import question_of
from app.evaluation.judge import CitedExcerpt, JudgeError, JudgeRequest, judge
from app.evaluation.models import LiveStatus, LiveVerdict, VerdictOutcome
from app.evaluation.ports import EvaluationPorts
from app.evaluation.settings import judge_model
from app.gateway.gateway import ModelGateway
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import cost
from app.runtime.runtime import DoneEvent

NO_EVALUATION_MODEL = (
    "The Organisation has neither an Evaluation Model nor a Default Model to judge with."
)

# The one random source the Live sample rate draws from.
_draws = random.Random()  # noqa: S311 (sampling, not security)


def seed_draws(seed: int | None) -> None:
    """Seeds the draws: the API and worker do at start, with ``Settings.live_sample_seed``."""
    _draws.seed(seed)


async def sample_reply(
    sessionmaker: async_sessionmaker[AsyncSession],
    agent_id: uuid.UUID,
    message_id: uuid.UUID,
    done: DoneEvent,
    *,
    clock: Clock,
) -> uuid.UUID | None:
    """Draws whether the stored Visitor reply ``message_id`` is judged; when it is, saves its
    ``pending`` Live Verdict and returns its ID, for the caller to send the task with."""
    if done.refused or done.fallback:
        return None
    async with sessionmaker() as session:
        rate = await session.scalar(
            select(Agent.live_sample_rate).where(Agent.id == agent_id, Agent.archived_at.is_(None))
        )
        # A draw falls under the rate as often as the rate says: never at 0, always at 100.
        if not rate or _draws.random() * 100 >= rate:
            return None
        message = await session.get_one(Message, message_id)
        verdict = LiveVerdict(
            id=uuid.uuid4(),
            organisation_id=message.organisation_id,
            message_id=message.id,
            agent_id=agent_id,
            # A Visitor reply is always an Agent Version's.
            agent_version_id=cast(uuid.UUID, message.agent_version_id),
            status=LiveStatus.PENDING,
            created_at=clock.now(),
        )
        session.add(verdict)
        await session.commit()
        return verdict.id


async def _request(session: AsyncSession, reply: Message) -> JudgeRequest:
    """What the judge is given: the question, the reply, and the Chunks the reply was given, split
    into those it cited and the rest."""
    question = await question_of(session, reply)
    given: dict[int, tuple[bool, CitedExcerpt]] = {}
    traced = await traced_chunks(session, reply)
    # Those left out (with no rank) weren't given to the model.
    for chunk in (c for c in traced if c.retrieval.rank is not None):
        rank = chunk.retrieval.rank
        excerpt = CitedExcerpt(
            f"C{rank}", chunk.document_name or "Deleted Document", chunk.text or ""
        )
        # A Chunk found again by a later Search keeps its first label.
        given.setdefault(cast(int, rank), (chunk.retrieval.cited, excerpt))
    return JudgeRequest(
        question=question.content,
        answer=reply.content,
        cited=[excerpt for cited, excerpt in given.values() if cited],
        reference_answer=None,
        grounding=True,
        answers_question=True,
        given=[excerpt for cited, excerpt in given.values() if not cited],
    )


def _outcome(passed: bool) -> VerdictOutcome:
    return VerdictOutcome.PASS if passed else VerdictOutcome.FAIL


async def judge_live_verdict(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    verdict_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Judges the pending Live Verdict: ``judged`` with both checks, or ``error`` with why."""
    async with sessionmaker() as session:
        verdict = await session.get_one(LiveVerdict, verdict_id)
        reply = await session.get_one(Message, verdict.message_id)
        request = await _request(session, reply)
        chosen = await judge_model(session, verdict.organisation_id)
        verdict.status = LiveStatus.ERROR
        if chosen is None:
            verdict.error_reason = NO_EVALUATION_MODEL
            await session.commit()
            return
        verdict.judge_provider = chosen.credential.provider
        verdict.judge_model = chosen.model
        try:
            judging = await judge(
                functools.partial(gateway.chat_model, chosen.credential, chosen.model),
                chosen.model,
                request,
                timeout_s=ports.judge_timeout_s,
            )
        except JudgeError as error:
            verdict.error_reason = error.message
            await session.commit()
            return
        now = clock.now()
        grounded = judging.verdicts["grounding"]
        answers = judging.verdicts["answers_question"]
        verdict.status = LiveStatus.JUDGED
        verdict.grounded = _outcome(grounded.passed)
        verdict.grounded_reason = grounded.reason
        verdict.answers_question = _outcome(answers.passed)
        verdict.answers_question_reason = answers.reason
        verdict.passed = grounded.passed and answers.passed
        verdict.input_tokens = judging.usage.input_tokens
        verdict.output_tokens = judging.usage.output_tokens
        pricing = await credential_pricing(session, chosen.credential)
        verdict.cost_usd = cost(
            pricing, chosen.model, judging.usage, now, await price_table(session)
        )
        verdict.judged_at = now
        await session.commit()


async def live_verdict_of(session: AsyncSession, message_id: uuid.UUID) -> LiveVerdict | None:
    """The reply's Live Verdict; None when it wasn't chosen."""
    return await session.scalar(select(LiveVerdict).where(LiveVerdict.message_id == message_id))
