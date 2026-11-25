"""Calls (spec 20, ADR-0019): a Visitor talking to an Agent inside their Conversation, with the
voice layer listening, taking turns and speaking, and our runtime writing every reply.

- ``start_call`` (the widget, with the Conversation token) runs admission control, records a
  Call (its Conversation, when it started and the Version that was Live), asks the voice layer
  to start it, and issues the Call token the widget hands the voice layer.
- ``turn_call`` checks a turn the voice layer sends to the turn endpoint: the Agent's per-Agent
  secret, then a good Call token for an open Call of one of that Agent's Conversations. A turn
  that fails either check is refused before anything is answered.
- ``end_call`` (the widget, with the Conversation token) records when the Conversation's open
  Call ended.
"""

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import serving
from app.agents.models import Agent
from app.conversations.models import Call, Conversation
from app.credentials.models import ProviderCredential
from app.credentials.service import open_secret
from app.embed import service
from app.embed.admission import Admission
from app.embed.tokens import TokenSigner
from app.voice.port import CallJoin, VoiceLayerError
from app.voice.remote import VoicePorts, call_secret


class CallsOffError(Exception):
    """The Agent doesn't take Calls: calling is off."""


class InvalidSecretError(Exception):
    """The turn didn't carry the Agent's per-Agent secret."""


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
    the Token Budget, as for a message, which the start counts against), and
    ``VoiceLayerError`` when the voice layer can't start it; nothing is recorded then."""
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
    call = Call(
        organisation_id=conversation.organisation_id,
        conversation_id=conversation.id,
        agent_version_id=found.live.agent_version_id,
        started_at=now,
        ip=ip,
    )
    session.add(call)
    await session.flush()
    try:
        join = await voice.layer.start_call(
            open_secret(voice.envelope, credential), str(agent.remote_agent_id)
        )
    except VoiceLayerError:
        await session.rollback()
        raise
    conversation.last_activity_at = now
    await session.commit()
    return StartedCall(call.id, signer.call(call.id, conversation.id, now=now), join)


async def end_call(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> None:
    """Ends the Conversation token's Conversation's open Call, recording when it ended; with no
    Call open, nothing changes. Raises ``service.InvalidTokenError`` for a bad token."""
    conversation = await service.visitor_conversation(session, signer, public_id, token, now=now)
    await session.execute(
        update(Call)
        .where(Call.conversation_id == conversation.id, Call.ended_at.is_(None))
        .values(ended_at=now)
    )
    await session.commit()


@dataclass(frozen=True)
class CallTurn:
    agent: Agent
    conversation: Conversation
    call: Call


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
    ``call_token`` is a good Call token for an open Call in one of the Agent's Conversations."""
    agent = await session.scalar(select(Agent).where(Agent.public_id == public_id))
    expected = None if agent is None else call_secret(voice.envelope, agent)
    if agent is None or expected is None:
        raise InvalidSecretError
    if not hmac.compare_digest(expected.encode(), secret.encode()):
        raise InvalidSecretError
    ids = signer.call_ids(call_token, now=now)
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
            )
        )
    ).first()
    if row is None or row[0].ended_at is not None:
        raise InvalidCallError
    call, conversation = row
    return CallTurn(agent, conversation, call)
