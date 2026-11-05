"""Creating, listing and reading a Project's Agents, and saving an Agent's Draft.

Every function takes an ``OrganisationScope`` and a Project ID, so an Agent is only found inside
its own Project of the Organisation the Member works in. Changes go through
``active_project``, so an archived Project's Agents can't be created or changed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentDraft
from app.projects.service import active_project, get_project
from app.tenancy.repository import OrganisationScope

CREATED = "agent.created"


class AgentNotFoundError(Exception):
    """No Agent with that ID in the Project."""


@dataclass(frozen=True)
class AgentWithDraft:
    agent: Agent
    draft: AgentConfig
    draft_updated_at: datetime


async def _with_draft(session: AsyncSession, agent: Agent) -> AgentWithDraft:
    draft = await session.get_one(AgentDraft, agent.id)
    return AgentWithDraft(agent, AgentConfig.model_validate(draft.config), draft.updated_at)


async def create_agent(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    name: str,
    now: datetime,
) -> AgentWithDraft:
    """Creates an Agent with a default Draft and records ``agent.created``."""
    project = await active_project(session, scope, project_id)
    agent = Agent(organisation_id=scope.organisation_id, project_id=project.id, name=name)
    session.add(agent)
    await session.flush()
    session.add(AgentDraft(agent_id=agent.id, config=AgentConfig().model_dump(), updated_at=now))
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=CREATED,
        target=audit.AuditTarget("agent", agent.id),
        after={"name": name, "project_id": str(project.id)},
        occurred_at=now,
    )
    await session.commit()
    await session.refresh(agent)
    return await _with_draft(session, agent)


async def list_agents(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID
) -> list[AgentWithDraft]:
    """The Project's Agents, oldest first."""
    project = await get_project(session, scope, project_id)
    agents = await session.scalars(
        select(Agent).where(Agent.project_id == project.id).order_by(Agent.created_at, Agent.id)
    )
    return [await _with_draft(session, agent) for agent in agents]


async def get_agent(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> AgentWithDraft:
    project = await get_project(session, scope, project_id)
    agent = await session.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.project_id == project.id)
    )
    if agent is None:
        raise AgentNotFoundError
    return await _with_draft(session, agent)


async def save_draft(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    config: AgentConfig,
    *,
    now: datetime,
) -> AgentWithDraft:
    """Replaces the Agent's Draft with ``config``."""
    await active_project(session, scope, project_id)
    found = await get_agent(session, scope, project_id, agent_id)
    draft = await session.get_one(AgentDraft, found.agent.id, with_for_update=True)
    draft.config = config.model_dump()
    draft.updated_at = now
    await session.commit()
    return AgentWithDraft(found.agent, config, now)
