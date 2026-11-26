"""Calls (spec 20, ADR-0019): a Visitor talking to an Agent inside their Conversation, with the
voice layer listening, taking turns and speaking, and our runtime writing every reply.

- ``start_call`` (the widget, with the Conversation token) runs admission control, records a
  Call (its Conversation, when it started and the Version that was Live), asks the voice layer
  to start it, and issues the Call token the widget hands the voice layer.
- ``turn_call`` checks a turn the voice layer sends to the turn endpoint: the Agent's per-Agent
  secret, then a good Call token for an open Call of one of that Agent's Conversations (or a
  Playground Call token for one of its Playground Calls, ``app.playground.calls``). A turn
  that fails either check is refused before anything is answered.
- ``end_call`` (the widget, with the Conversation token) ends the Conversation's open Call.
- ``interrupt`` (the widget, with the Conversation token) marks the reply the Visitor talked
  over as interrupted.
- ``end_unavailable`` ends a Call whose turn the Agent couldn't answer.

The Call limits (``app.embed.call_limits``) bound both: admission refuses a second Call in the
Conversation, a third for the IP address and any once the day's Call minutes are spent, and
ending a Call counts its minutes.
"""

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import serving
from app.agents.models import Agent
from app.conversations.models import Call, Conversation, Message
from app.credentials.models import ProviderCredential
from app.embed import call_limits, service
from app.embed.admission import Admission
from app.embed.call_limits import CallEnd, CallRefusal
from app.embed.tokens import TokenSigner
from app.voice import remote
from app.voice.port import CallJoin
from app.voice.remote import VoicePorts, call_secret


class CallsOffError(Exception):
    """The Agent doesn't take Calls: calling is off."""


class InvalidSecretError(Exception):
    """The turn didn't carry the Agent's per-Agent secret."""


class CallNotAdmittedError(Exception):
    """The Call limits refused the Call: the Conversation has one open, the IP address holds
    the platform's cap of open Calls, or the Agent's Call minutes budget is spent for today."""

    def __init__(self, reason: CallRefusal, agent_id: uuid.UUID) -> None:
        super().__init__(reason)
        self.reason = reason
        self.agent_id = agent_id


class InvalidCallError(Exception):
    """The turn's Call token is missing, tampered with, expired, for another Conversation or
    Agent, or its Call has ended."""


@dataclass(frozen=True)
class StartedCall:
    call_id: uuid.UUID
    # Signed, bound to the Call and its Conversation; the voice layer sends it with each turn.
    call_token: str
    # What the browser needs to join the Call in the voice layer.
    join: CallJoin
    # The Maximum Call length it started under: the platform ends it then.
    max_call_minutes: int


async def start_call(
    session: AsyncSession,
    signer: TokenSigner,
    public_id: str,
    token: str,
    *,
    admission: Admission,
    voice: VoicePorts,
    ip: str,
    now: datetime,
) -> StartedCall:
    """Starts a Call in the Conversation token's Conversation. Raises
    ``service.InvalidTokenError`` for a bad Conversation token, ``serving.AgentNotServedError``
    or ``serving.AgentNotLiveError`` once the Agent is retired, ``CallsOffError`` when it doesn't
    take Calls, ``service.NotAdmittedError`` when admission control refuses (the rate limits and
    the Token Budget, as for a message, which the start counts against),
    ``CallNotAdmittedError`` when the Call limits refuse it, and ``VoiceLayerError`` when the
    voice layer can't start it; nothing is recorded then, but the Agent's Calls failing
    alert is raised. A Call that starts clears it."""
    conversation = await service.visitor_conversation(session, signer, public_id, token, now=now)
    found = await serving.live_agent(session, public_id)
    agent = found.agent
    credential = (
        None
        if agent.call_credential_id is None
        else await session.get(ProviderCredential, agent.call_credential_id)
    )
    if not service.takes_calls(agent) or credential is None:
        raise CallsOffError
    refusal = await admission.admit(service.limits_of(agent), conversation.id, ip)
    if refusal is not None:
        raise service.NotAdmittedError(refusal, agent.id)
    limited = await call_limits.refusal(session, agent, conversation, ip, now=now)
    if limited is not None:
        agent_id = agent.id
        await session.rollback()
        raise CallNotAdmittedError(limited, agent_id)
    call = Call(
        organisation_id=conversation.organisation_id,
        conversation_id=conversation.id,
        agent_version_id=found.live.agent_version_id,
        started_at=now,
        ip=ip,
        max_call_minutes=agent.max_call_minutes,
    )
    # The spoken greeting opens a Conversation with no Messages; any other Call opens listening.
    greet = (
        await session.scalar(
            select(Message.id).where(Message.conversation_id == conversation.id).limit(1)
        )
        is None
    )
    session.add(call)
    await session.flush()
    join = await remote.start_call(session, voice, agent, credential, greet=greet, now=now)
    conversation.last_activity_at = now
    max_call_minutes = call.max_call_minutes
    await session.commit()
    expires_at = now + timedelta(minutes=max_call_minutes)
    return StartedCall(
        call.id,
        signer.call(call.id, conversation.id, expires_at=expires_at),
        join,
        max_call_minutes,
    )


async def end_call(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> None:
    """Ends the Conversation token's Conversation's open Call, recording when it ended and its
    minutes; with no Call open, nothing changes. Raises ``service.InvalidTokenError`` for a bad
    token."""
    conversation = await service.visitor_conversation(session, signer, public_id, token, now=now)
    await call_limits.end_open_call(session, conversation, now=now, reason=CallEnd.VISITOR)
    await session.commit()


async def interrupt(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> None:
    """Marks the reply being spoken in the token's Conversation's open Call as interrupted: the
    Visitor talked over it. That is the reply to the Visitor's latest words in the Call. Saved
    already, it is marked now; still being answered, the Call records the turn and the reply is
    marked when it is saved (``app.playground.service.answer``). Either way it keeps its whole
    text. With no Call open, or no words said in it yet (the greeting is being spoken), nothing
    changes. Raises ``service.InvalidTokenError`` for a bad token."""
    conversation = await service.visitor_conversation(session, signer, public_id, token, now=now)
    # Locked, as saving a reply of the Call locks it: the reply is either saved first (and
    # found here) or sees the turn recorded.
    call = await session.scalar(
        select(Call)
        .where(Call.conversation_id == conversation.id, Call.ended_at.is_(None))
        .with_for_update()
    )
    said = None
    if call is not None:
        said = await session.scalar(
            select(Message)
            .where(Message.call_id == call.id, Message.role == "user")
            .order_by(Message.seq.desc())
            .limit(1)
        )
    if call is not None and said is not None:
        reply = await session.scalar(
            select(Message).where(
                Message.call_id == call.id,
                Message.role == "assistant",
                Message.seq > said.seq,
            )
        )
        if reply is None:
            call.interrupted_turn_id = said.id
        else:
            reply.interrupted = True
    await session.commit()


async def end_unavailable(
    session: AsyncSession, conversation_id: uuid.UUID, *, now: datetime
) -> None:
    """Ends the Conversation's open Call because the Agent couldn't answer its turn: the
    Visitor heard the Unavailable text, and the widget returns them to messaging."""
    conversation = await session.get_one(Conversation, conversation_id)
    await call_limits.end_open_call(session, conversation, now=now, reason=CallEnd.UNAVAILABLE)
    await session.commit()


@dataclass(frozen=True)
class CallTurn:
    agent: Agent
    conversation: Conversation
    call: Call

    @property
    def playground(self) -> bool:
        """A Playground Call: the Draft answers its turns, outside the Visitor limits."""
        return self.conversation.is_playground


async def turn_call(
    session: AsyncSession,
    signer: TokenSigner,
    voice: VoicePorts,
    public_id: str,
    secret: str,
    call_token: str,
    *,
    now: datetime,
) -> CallTurn:
    """The open Call a turn the voice layer sent belongs to. Raises ``InvalidSecretError``
    unless ``secret`` is the Agent's per-Agent secret, and ``InvalidCallError`` unless
    ``call_token`` is a good Call token for an open Call in one of the Agent's Visitor
    Conversations, or a good Playground Call token for an open Call in one of its Playground
    Conversations (``CallTurn.playground``).
    A Call past its deadline (``call_limits.deadline``) that Beat hasn't ended yet is ended
    here, then, and the turn refused. Saving the Visitor's words checks again, under the
    Call's lock, that it is still open (``app.playground.service.save_question``), so a Call
    that ends after this check takes no Spoken Message and no reply."""
    agent = await session.scalar(select(Agent).where(Agent.public_id == public_id))
    expected = None if agent is None else call_secret(voice.envelope, agent)
    if agent is None or expected is None:
        raise InvalidSecretError
    if not hmac.compare_digest(expected.encode(), secret.encode()):
        raise InvalidSecretError
    playground = False
    ids = signer.call_ids(call_token, now=now)
    if ids is None:
        playground = True
        ids = signer.playground_call_ids(call_token, now=now)
    if ids is None:
        raise InvalidCallError
    call_id, conversation_id = ids
    row = (
        await session.execute(
            select(Call, Conversation)
            .join(Conversation, Conversation.id == Call.conversation_id)
            .where(
                Call.id == call_id,
                Call.conversation_id == conversation_id,
                Conversation.agent_id == agent.id,
                # A Call token stands only for a Visitor's Call, and a Playground Call token
                # only for a Playground Call.
                Conversation.is_playground.is_(playground),
            )
            # Locks the Call, so it can't end between here and the commit: a turn racing its
            # end waits, then finds it ended.
            .with_for_update(of=Call)
        )
    ).first()
    if row is None or row[0].ended_at is not None:
        raise InvalidCallError
    call, conversation = row
    if await call_limits.past_deadline(session, call, conversation, now=now):
        await session.commit()
        raise InvalidCallError
    # The Call isn't silent: Beat leaves it open for another minute.
    call.last_turn_at = now
    await session.commit()
    return CallTurn(agent, conversation, call)
