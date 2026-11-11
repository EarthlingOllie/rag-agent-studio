"""Serving an Agent's Live Version: the runtime contract the embed widget (spec 06) calls.

A Visitor is answered by the Live Version's AgentConfig and the text of the Project
Instructions Version it pins, never by the Draft. Each answer records that Version
(``config_source`` ``version`` and ``agent_version_id``), so metrics and Traces point at the
configuration that actually served it. An Agent with no Version is not live and serves nothing;
nor does an archived Agent or an Agent of an archived Project.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.versions import Served, served
from app.conversations.models import Conversation, Message
from app.playground.service import PreparedTurn, save_question
from app.projects.models import Project


class AgentNotServedError(Exception):
    """No active Agent with that public ID in an active Project."""


class AgentNotLiveError(Exception):
    """The Agent has never been published, so it has no Live Version to serve."""


@dataclass(frozen=True)
class LiveAgent:
    agent: Agent
    project: Project
    live: Served


async def live_agent(session: AsyncSession, public_id: str) -> LiveAgent:
    """The Agent a Visitor addresses by its public ID, with its Live Version."""
    row = (
        await session.execute(
            select(Agent, Project)
            .join(Project, Project.id == Agent.project_id)
            .where(
                Agent.public_id == public_id,
                Agent.archived_at.is_(None),
                Project.archived_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise AgentNotServedError
    agent, project = row
    live = await served(session, agent)
    if live is None:
        raise AgentNotLiveError
    return LiveAgent(agent, project, live)


async def start_conversation(session: AsyncSession, public_id: str, *, now: datetime) -> uuid.UUID:
    """Starts a Visitor Conversation with a live Agent; returns its ID."""
    found = await live_agent(session, public_id)
    conversation = Conversation(
        organisation_id=found.agent.organisation_id,
        agent_id=found.agent.id,
        is_playground=False,
        last_activity_at=now,
        # It started now, by the app's clock (the Conversations list filters on it).
        created_at=now,
    )
    session.add(conversation)
    await session.commit()
    return conversation.id


async def prepare_turn(
    session: AsyncSession,
    public_id: str,
    conversation_id: uuid.UUID,
    question: str,
    *,
    now: datetime,
) -> PreparedTurn:
    """Saves a Visitor's question, ready for ``app.playground.service.answer`` to answer with
    the Live Version."""
    found = await live_agent(session, public_id)
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.agent_id == found.agent.id,
            Conversation.is_playground.is_(False),
            # Deleted on request: it takes no more questions.
            Conversation.deleted_at.is_(None),
        )
    )
    if conversation is None:
        raise AgentNotServedError
    messages = await session.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
    )
    return await save_question(
        session,
        found.project,
        conversation,
        list(messages),
        found.live.config,
        found.live.instructions,
        question,
        agent_version_id=found.live.agent_version_id,
        now=now,
    )
