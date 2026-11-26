"""Live Verdicts (spec 15): choosing Visitor replies by the Agent's Live sample rate, and judging a
chosen one in the background with the Evaluation Model.

Choosing happens after a Visitor reply is stored and sent, so it never delays or changes it. A
reply is a candidate unless it is a Guardrail block or the Fallback Text, and only while its
Agent isn't archived; a draw from the one module-level random source chooses it with the
Agent's Live sample rate, while the Organisation's Evaluation budget for the month isn't spent
(``app.evaluation.budget``). The draw is seeded from ``Settings.live_sample_seed``, which tests
set, so a sampled subset is stable. A chosen reply gets a ``pending`` Live Verdict, committed
before its task is sent. The Playground never calls this: only the widget's replies are sampled.

The task judges the question, the reply, its Remembered turns (as its Agent Version remembered
them) and the Chunks the reply was given (cited and not), each in its own data block, through the
Model gateway with the Evaluation Model (or the Default Model, as for Evaluation Runs): spec 14's
judge, asked for ``grounding`` and ``answers_question`` in one
structured-output call at temperature 0. The system prompt and Project Instructions are never
sent. The reply passes when both checks pass. A judge error or timeout makes the Live Verdict an
``error`` with its reason, as does any unexpected error; there is no retry, so an outage doesn't
multiply spend. The job acts only on a ``pending`` Live Verdict, and stores its outcome with one
conditional update that also gates the spend, so however often the job runs, and however many
copies race, the judgement is charged once; no row is locked across the judge call. The judge's
Cost is frozen with the cost function and Price table in force when it is judged, and added to
the Organisation's monthly spend; the judgement that spends the budget emails its Owners once.
When the reply, its question or a Remembered turn has been Purged before judging, the Live
Verdict is ``skipped`` and nothing is sent to the judge.
"""

import functools
import itertools
import logging
import random
import uuid
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentVersion
from app.alert_emails.delivery import send_alert_emails
from app.conversations.models import Message, MessageRole
from app.conversations.service import traced_chunks
from app.core.clock import Clock
from app.evaluation.budget import add_spend, raise_budget_spent, read_budget
from app.evaluation.from_message import question_of
from app.evaluation.judge import CitedExcerpt, JudgeError, JudgeRequest, judge
from app.evaluation.models import LiveStatus, LiveVerdict, VerdictOutcome
from app.evaluation.ports import EvaluationPorts
from app.evaluation.settings import judge_model
from app.gateway.gateway import ModelGateway
from app.guardrails.outcomes import blocked
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import cost
from app.runtime.prompt import Turn
from app.runtime.runtime import DoneEvent

NO_EVALUATION_MODEL = (
    "The Organisation has neither an Evaluation Model nor a Default Model to judge with."
)

UNEXPECTED = "Judging stopped on an unexpected error; this reply is left out of the Live score."

logger = logging.getLogger(__name__)

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
        found = (
            await session.execute(
                select(Agent.live_sample_rate, Agent.organisation_id).where(
                    Agent.id == agent_id, Agent.archived_at.is_(None)
                )
            )
        ).one_or_none()
        if found is None or not found.live_sample_rate:
            return None
        # Nothing is chosen without an Evaluation budget, or once the month's is spent.
        now = clock.now()
        if not (await read_budget(session, found.organisation_id, now)).allows_sampling:
            return None
        # A draw falls under the rate as often as the rate says: never at 0, always at 100.
        if _draws.random() * 100 >= found.live_sample_rate:
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
            created_at=now,
        )
        session.add(verdict)
        await session.commit()
        return verdict.id


async def remembered_turns(
    session: AsyncSession, reply: Message, question: Message
) -> list[tuple[Message, Message]]:
    """The reply's Remembered turns, oldest first, as its Agent Version remembered them: the
    last of the earlier exchanges, leaving out those the input Guardrail blocked and those
    already Purged when the reply was given (neither was sent to the model)."""
    version = await session.get_one(AgentVersion, reply.agent_version_id)
    count = AgentConfig.model_validate(version.config).behaviour.remembered_turns
    earlier = await session.scalars(
        select(Message)
        .where(Message.conversation_id == reply.conversation_id, Message.seq < question.seq)
        .order_by(Message.seq)
    )
    turns = [
        (asked, answer)
        for asked, answer in itertools.pairwise(earlier)
        if (asked.role, answer.role) == (MessageRole.USER, MessageRole.ASSISTANT)
        and not blocked(answer.guardrail_outcomes)
        and all(m.purged_at is None or m.purged_at > reply.created_at for m in (asked, answer))
    ]
    return turns[-count:] if count else []


async def _request(session: AsyncSession, reply: Message) -> JudgeRequest | None:
    """What the judge is given: the reply's Remembered turns, the question, the reply, and the
    Chunks the reply was given, split into those it cited and the rest. None when the reply's
    text, its question's or a Remembered turn's has been Purged since: nothing is judged
    without its text."""
    question = await question_of(session, reply)
    turns = await remembered_turns(session, reply, question)
    texts = [reply, question, *(m for turn in turns for m in turn)]
    if any(m.purged_at is not None for m in texts):
        return None
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
        earlier_turns=[Turn(asked.content, answer.content) for asked, answer in turns],
    )


def _outcome(passed: bool) -> VerdictOutcome:
    return VerdictOutcome.PASS if passed else VerdictOutcome.FAIL


async def _settle(session: AsyncSession, verdict_id: uuid.UUID, **values: Any) -> bool:
    """Stores the Live Verdict's outcome only while it is still ``pending``, in the caller's
    transaction; whether it did. The one conditional update a copy of the job wins: a copy
    that finds it settled already stores nothing and records no spend."""
    settled = await session.scalar(
        update(LiveVerdict)
        .where(LiveVerdict.id == verdict_id, LiveVerdict.status == LiveStatus.PENDING)
        .values(**values)
        .returning(LiveVerdict.id)
    )
    return settled is not None


async def _judge_pending(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    verdict_id: uuid.UUID,
    clock: Clock,
) -> None:
    async with sessionmaker() as session:
        verdict = await session.get_one(LiveVerdict, verdict_id)
        if verdict.status != LiveStatus.PENDING:
            # Settled by an earlier copy of the job: nothing is judged or charged again.
            return
        reply = await session.get_one(Message, verdict.message_id)
        request = await _request(session, reply)
        if request is None:
            # Purged before it was judged: nothing is sent to the judge.
            await _settle(session, verdict_id, status=LiveStatus.SKIPPED)
            await session.commit()
            return
        chosen = await judge_model(session, verdict.organisation_id)
        if chosen is None:
            await _settle(
                session, verdict_id, status=LiveStatus.ERROR, error_reason=NO_EVALUATION_MODEL
            )
            await session.commit()
            return
        judged_by = {"judge_provider": chosen.credential.provider, "judge_model": chosen.model}
        pricing = await credential_pricing(session, chosen.credential)
        table = await price_table(session)
        # Only reads so far: no row is locked while the judge is asked.
        await session.commit()
        try:
            judging = await judge(
                functools.partial(gateway.chat_model, chosen.credential, chosen.model),
                chosen.model,
                request,
                timeout_s=ports.judge_timeout_s,
            )
        except JudgeError as error:
            await _settle(
                session,
                verdict_id,
                status=LiveStatus.ERROR,
                error_reason=error.message,
                **judged_by,
            )
            await session.commit()
            return
        now = clock.now()
        grounded = judging.verdicts["grounding"]
        answers = judging.verdicts["answers_question"]
        cost_usd = cost(pricing, chosen.model, judging.usage, now, table)
        if not await _settle(
            session,
            verdict_id,
            status=LiveStatus.JUDGED,
            grounded=_outcome(grounded.passed),
            grounded_reason=grounded.reason,
            answers_question=_outcome(answers.passed),
            answers_question_reason=answers.reason,
            passed=grounded.passed and answers.passed,
            input_tokens=judging.usage.input_tokens,
            output_tokens=judging.usage.output_tokens,
            cost_usd=cost_usd,
            judged_at=now,
            **judged_by,
        ):
            # Another copy settled it while this one judged: its spend is the one recorded.
            await session.rollback()
            return
        # The reply may have been Purged while it was judged. The Purge clears the Live Verdict
        # in the same pass as the Message, so with the Live Verdict now locked by the update a
        # fresh read of the Message says whether the reasons, which can quote the Visitor, may
        # be kept.
        purged_at = await session.scalar(select(Message.purged_at).where(Message.id == reply.id))
        if purged_at is not None:
            await session.execute(
                update(LiveVerdict)
                .where(LiveVerdict.id == verdict_id)
                .values(grounded_reason=None, answers_question_reason=None, purged_at=purged_at)
            )
        # A Cost with no known price adds nothing to the month's spend.
        spent = cost_usd is not None and await add_spend(
            session, verdict.organisation_id, cost_usd, now
        )
        emails = (
            await raise_budget_spent(
                session, verdict.organisation_id, now, studio_url=ports.studio_url
            )
            if spent
            else []
        )
        await session.commit()
        await send_alert_emails(session, ports.mailer, now=now, ids=emails)


async def judge_live_verdict(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    verdict_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Judges the Live Verdict while it is ``pending``: ``judged`` with both checks, ``error``
    with why, or ``skipped`` when the text it needs was Purged first. One already settled is
    left, so a second run of the job judges and charges nothing. An unexpected error makes it an
    ``error`` too, never leaving it ``pending``."""
    try:
        await _judge_pending(sessionmaker, ports, gateway, verdict_id, clock)
    except Exception:
        logger.exception(
            "Judging a Live Verdict failed", extra={"live_verdict_id": str(verdict_id)}
        )
        async with sessionmaker() as session:
            await _settle(session, verdict_id, status=LiveStatus.ERROR, error_reason=UNEXPECTED)
            await session.commit()


async def live_verdict_of(session: AsyncSession, message_id: uuid.UUID) -> LiveVerdict | None:
    """The reply's Live Verdict; None when it wasn't chosen."""
    return await session.scalar(select(LiveVerdict).where(LiveVerdict.message_id == message_id))
