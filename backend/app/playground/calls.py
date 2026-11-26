"""Playground Calls (spec 20): an Editor calls the Agent's Draft from the Playground, to hear it
before Visitors do.

A Playground Call uses the Agent's Call settings and its remote agent in the voice layer, and its
turns reach the same turn endpoint as a Visitor's, with a Playground Call token instead of a Call
token. They are answered by the Draft, with the Project Instructions the Editor picked when the
Call started (the Instructions Draft, or an Instructions Version), and saved as Spoken Messages
of the Playground Conversation, each with its Trace and Cost.

Like typed Playground questions they are outside the Visitor limits: no rate limits, Token
Budget or Call minutes budget, and no Live Verdicts. A Playground Call still ends as any Call
does (the Editor, the Maximum Call length, silence, an answer the Draft couldn't give), and its
Voice Cost is frozen then; it counts in Organisation cost, as its replies' model Cost does.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import RetrievalMode
from app.agents.models import Agent
from app.agents.service import AgentArchivedError, active_agent, get_agent, with_draft
from app.conversations.models import Call, Conversation, Message
from app.credentials.models import ProviderCredential
from app.credentials.service import open_secret
from app.embed import call_limits
from app.embed.call_limits import CallEnd
from app.embed.calls import CallsOffError, StartedCall
from app.embed.service import takes_calls
from app.embed.tokens import TokenSigner
from app.embed.visitor_turn import ServedTurn, ServingPorts
from app.playground.service import answer, get_conversation, save_question
from app.projects.instructions import project_version
from app.projects.models import InstructionsVersion, Project
from app.projects.service import active_project
from app.tenancy.repository import OrganisationScope
from app.voice.port import VoiceLayerError
from app.voice.remote import VoicePorts


class CallOpenError(Exception):
    """The Playground Conversation already has a Call open."""


async def start_call(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    instructions_version_id: uuid.UUID | None,
    signer: TokenSigner,
    voice: VoicePorts,
    now: datetime,
) -> StartedCall:
    """Starts a Call with the Draft in the Playground Conversation, answering with the
    Instructions Draft or the Instructions Version named. Raises the Playground's not-found and
    archived errors, ``InstructionsVersionNotFoundError`` for a Version not in the Project,
    ``CallsOffError`` when the Agent's calling is off, ``CallOpenError`` when the Conversation has
    a Call open, and ``VoiceLayerError`` when the voice layer can't start it; nothing is recorded
    then."""
    project = await active_project(session, scope, project_id)
    version = (
        None
        if instructions_version_id is None
        else await project_version(session, project, instructions_version_id)
    )
    agent = (await active_agent(session, scope, project_id, agent_id)).agent
    conversation, messages = await get_conversation(
        session, scope, project_id, agent_id, conversation_id
    )
    credential = (
        None
        if agent.call_credential_id is None
        else await session.get(ProviderCredential, agent.call_credential_id)
    )
    if not takes_calls(agent) or credential is None:
        raise CallsOffError
    # Locked, so two starts can't both find the Conversation without a Call.
    await session.refresh(conversation, with_for_update=True)
    open_here = await session.scalar(
        select(Call.id).where(Call.conversation_id == conversation.id, Call.ended_at.is_(None))
    )
    if open_here is not None:
        await session.rollback()
        raise CallOpenError
    call = Call(
        organisation_id=conversation.organisation_id,
        conversation_id=conversation.id,
        agent_version_id=None,
        instructions_version_id=None if version is None else version.id,
        started_at=now,
        # The voice layer's turns are an Editor's, outside the Visitor rate limits: no address.
        ip="",
        max_call_minutes=agent.max_call_minutes,
    )
    session.add(call)
    await session.flush()
    try:
        join = await voice.layer.start_call(
            open_secret(voice.envelope, credential),
            str(agent.remote_agent_id),
            # The spoken greeting opens a Conversation with no Messages, as in the widget.
            greet=not messages,
        )
    except VoiceLayerError:
        await session.rollback()
        raise
    conversation.last_activity_at = now
    max_call_minutes = call.max_call_minutes
    await session.commit()
    expires_at = now + timedelta(minutes=max_call_minutes)
    return StartedCall(
        call.id,
        signer.playground_call(call.id, conversation.id, expires_at=expires_at),
        join,
        max_call_minutes,
    )


async def end_call(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    now: datetime,
) -> None:
    """Ends the Playground Conversation's open Call, freezing its minutes and Voice Cost; with no
    Call open, nothing changes. An archived Agent's Call can still be ended."""
    await get_agent(session, scope, project_id, agent_id)
    conversation, _ = await get_conversation(session, scope, project_id, agent_id, conversation_id)
    await call_limits.end_open_call(session, conversation, now=now, reason=CallEnd.EDITOR)
    await session.commit()


async def serve_turn(
    session: AsyncSession,
    agent: Agent,
    conversation: Conversation,
    call: Call,
    words: str,
    *,
    ports: ServingPorts,
) -> ServedTurn:
    """Saves the Editor's words in the Playground Call and returns the stream answering them
    with the Draft and the Call's Project Instructions, as a typed Playground question is
    answered: no admission control, Token Budget or Live Verdict. Raises
    ``AgentArchivedError`` once the Agent or its Project is archived, and the model
    resolution errors when the Draft has no model to answer with."""
    project = await session.get_one(Project, agent.project_id)
    if project.archived_at is not None or agent.archived_at is not None:
        # The Playground is off while either is archived.
        raise AgentArchivedError
    draft = (await with_draft(session, agent)).draft
    version = (
        None
        if call.instructions_version_id is None
        else await session.get_one(InstructionsVersion, call.instructions_version_id)
    )
    messages = list(
        await session.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
        )
    )
    prepared = await save_question(
        session,
        project,
        conversation,
        messages,
        draft,
        project.instructions if version is None else version.markdown,
        words,
        agent_version_id=None,
        instructions_version=version,
        call_id=call.id,
        now=ports.clock.now(),
    )
    config = prepared.config
    return ServedTurn(
        answer(
            prepared,
            sessionmaker=ports.sessionmaker,
            gateway=ports.gateway,
            guardrails=ports.guardrails,
            embedders=ports.embedders,
            clock=ports.clock,
            searches=True,
        ),
        retractable=config.retrieval.mode is RetrievalMode.AGENTIC,
        searching_status=config.experience.ui_text.searching_status,
    )
