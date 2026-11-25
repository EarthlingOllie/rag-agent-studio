"""Serving a Visitor turn: the one path every Visitor message takes, whatever carries it.

``serve_turn`` takes the Agent, the Visitor's Conversation, the Visitor's words and their IP
address, and the Call they were said in when they were spoken. It runs admission control (the
rate limits and the Token Budget), saves the words against the Agent's Live Version and its
pinned Instructions, and answers them with the runtime, which saves the reply with its Message
attribution, Trace and Cost. It then counts the reply's usage against the Token Budget and draws
whether the reply gets a Live Verdict.

Awaiting it settles admission and the Live Version: a retired Agent, or one with no model to
answer with, raises there, so callers can still answer with a plain HTTP error. What it returns
yields ``Unavailable`` when admission control refused the words (nothing is saved), else the
runtime's events. The caller only turns those into its own wire format (the widget's
Server-Sent Events, or the turn endpoint's OpenAI-compatible chunks for a Call).
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.models import Agent
from app.conversations.models import Conversation
from app.core.clock import Clock
from app.embed import service
from app.embed.admission import Admission, Refusal
from app.embeddings.port import Embedder
from app.evaluation.live import sample_reply
from app.gateway.gateway import ModelGateway
from app.guardrails.pipeline import GuardrailPipeline
from app.mail.port import Mailer
from app.playground.service import Answered, AnswerEvent, answer
from app.runtime.runtime import CitationEvent, SearchEvent


@dataclass(frozen=True)
class Unavailable:
    """Admission control refused the Visitor's words: they get the Agent's unavailable text."""

    reason: Refusal


VisitorTurnEvent = Unavailable | AnswerEvent | SearchEvent


@dataclass(frozen=True)
class ServingPorts:
    """What serving a Visitor turn needs from the running app."""

    sessionmaker: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    guardrails: GuardrailPipeline
    embedders: dict[str, Embedder]
    clock: Clock
    admission: Admission
    mailer: Mailer
    # Where the Token Budget alert's email links to.
    studio_url: str
    # Sends a reply chosen for a Live Verdict to be judged in the background.
    enqueue_live_verdict: Callable[[uuid.UUID], Awaitable[None]]


async def serve_turn(
    session: AsyncSession,
    agent: Agent,
    conversation: Conversation,
    words: str,
    ip: str,
    *,
    ports: ServingPorts,
    call_id: uuid.UUID | None = None,
) -> AsyncIterator[VisitorTurnEvent]:
    """Admits and saves the Visitor's words; returns the stream that answers them with the
    Agent's Live Version. Words said in a Call (``call_id``) and their answer are saved as
    Spoken Messages of that Call. The first refusal or reply that finds the day's Token Budget spent
    raises the Agent's alert and emails its Owners, once per day."""
    agent_id = agent.id
    try:
        admitted = await service.admit_turn(
            session,
            agent,
            conversation,
            words,
            admission=ports.admission,
            ip=ip,
            call_id=call_id,
            now=ports.clock.now(),
        )
    except service.NotAdmittedError as refused:
        if refused.reason is Refusal.TOKEN_BUDGET:
            await _budget_exhausted(session, agent_id, ports)
        return _refused(refused.reason)
    return _answered(admitted, ports)


async def _refused(reason: Refusal) -> AsyncIterator[VisitorTurnEvent]:
    yield Unavailable(reason)


async def _answered(
    admitted: service.AdmittedTurn, ports: ServingPorts
) -> AsyncIterator[VisitorTurnEvent]:
    """The runtime's events for an admitted turn. Citations are passed on only when the Live
    Version shows them."""
    prepared = admitted.turn
    async for event in answer(
        prepared,
        sessionmaker=ports.sessionmaker,
        gateway=ports.gateway,
        guardrails=ports.guardrails,
        embedders=ports.embedders,
        clock=ports.clock,
        searches=True,
    ):
        if isinstance(event, CitationEvent) and not prepared.config.retrieval.citations:
            continue
        if not isinstance(event, Answered):
            yield event
            continue
        # The reply's actual usage counts against today's Token Budget; the reply that spends
        # it raises the alert.
        used = event.event.input_tokens + event.event.output_tokens
        total = await ports.admission.record_usage(admitted.limits.public_id, used)
        if total >= admitted.limits.daily_token_budget:
            async with ports.sessionmaker() as session:
                await _budget_exhausted(session, admitted.agent_id, ports)
        yield event
        # Only once the reply is stored and sent: it may be chosen for a Live Verdict, judged
        # in the background.
        chosen = await sample_reply(
            ports.sessionmaker, admitted.agent_id, event.message_id, event.event, clock=ports.clock
        )
        if chosen is not None:
            await ports.enqueue_live_verdict(chosen)


async def _budget_exhausted(
    session: AsyncSession, agent_id: uuid.UUID, ports: ServingPorts
) -> None:
    await service.budget_exhausted(
        session,
        agent_id,
        mailer=ports.mailer,
        studio_url=ports.studio_url,
        now=ports.clock.now(),
    )
