"""Creating, listing and reading a Project's Agents, saving an Agent's Draft, and archiving,
restoring and permanently deleting an Agent.

Every function takes an ``OrganisationScope`` and a Project ID, so an Agent is only found inside
its own Project of the Organisation the Member works in. Changes go through
``active_project``, so an archived Project's Agents can't be created or changed; an archived
Agent's Draft can't be changed either, and it starts no Playground Conversation.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentDraft
from app.agents.validation import check_draft
from app.conversations.models import Conversation
from app.projects.service import active_project, get_project
from app.tenancy.repository import OrganisationScope

CREATED = "agent.created"
ARCHIVED = "agent.archived"
RESTORED = "agent.restored"
DELETED = "agent.deleted"


class AgentNotFoundError(Exception):
    """No Agent with that ID in the Project."""


class AgentArchivedError(Exception):
    """The Agent is archived, so it can't be changed or used until an Owner restores it."""


class AgentNotArchivedError(Exception):
    """Only an archived Agent can be restored or permanently deleted."""


class AgentNameMismatchError(Exception):
    """The name typed to confirm a permanent deletion isn't the Agent's name."""


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
    session.add(
        AgentDraft(
            agent_id=agent.id,
            organisation_id=scope.organisation_id,
            config=AgentConfig().model_dump(mode="json"),
            updated_at=now,
        )
    )
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
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    archived: bool = False,
) -> list[AgentWithDraft]:
    """The Project's active Agents, oldest first, or with ``archived`` its archived ones."""
    project = await get_project(session, scope, project_id)
    archived_filter = Agent.archived_at.is_not(None) if archived else Agent.archived_at.is_(None)
    agents = await session.scalars(
        select(Agent)
        .where(Agent.project_id == project.id, archived_filter)
        .order_by(Agent.created_at, Agent.id)
    )
    return [await _with_draft(session, agent) for agent in agents]


async def _find(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Agent:
    project = await get_project(session, scope, project_id)
    query = select(Agent).where(Agent.id == agent_id, Agent.project_id == project.id)
    agent = await session.scalar(query.with_for_update() if lock else query)
    if agent is None:
        raise AgentNotFoundError
    return agent


async def get_agent(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> AgentWithDraft:
    """The Agent, archived or not."""
    return await _with_draft(session, await _find(session, scope, project_id, agent_id))


async def active_agent(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> AgentWithDraft:
    """The Agent, refused with ``AgentArchivedError`` while it is archived."""
    found = await get_agent(session, scope, project_id, agent_id)
    if found.agent.archived_at is not None:
        raise AgentArchivedError
    return found


async def _set_archived(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
    archive: bool,
) -> AgentWithDraft:
    await active_project(session, scope, project_id)
    agent = await _find(session, scope, project_id, agent_id, lock=True)
    was_archived = agent.archived_at is not None
    if was_archived == archive:
        raise AgentArchivedError if archive else AgentNotArchivedError
    agent.archived_at = now if archive else None
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=ARCHIVED if archive else RESTORED,
        target=audit.AuditTarget("agent", agent.id),
        before={"name": agent.name, "archived": was_archived},
        after={"name": agent.name, "archived": archive},
        occurred_at=now,
    )
    await session.commit()
    return await _with_draft(session, agent)


async def archive_agent(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> AgentWithDraft:
    """Archives the Agent, keeping its Draft and Conversations, and records ``agent.archived``.
    It leaves the Agents list and starts no new Playground Conversation."""
    return await _set_archived(session, scope, project_id, agent_id, now=now, archive=True)


async def restore_agent(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> AgentWithDraft:
    """Restores an archived Agent to the Agents list and records ``agent.restored``. Owners
    only; the route checks the role."""
    return await _set_archived(session, scope, project_id, agent_id, now=now, archive=False)


async def delete_agent(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    confirm_name: str,
    now: datetime,
) -> None:
    """Permanently deletes an archived Agent once ``confirm_name`` is its name, exactly, and
    records ``agent.deleted``. Its Draft, Conversations, Messages and their Trace rows go with
    it through the foreign keys' ``ON DELETE CASCADE``, so the credentials it named are no
    longer referenced. Owners only; the route checks the role."""
    await active_project(session, scope, project_id)
    agent = await _find(session, scope, project_id, agent_id, lock=True)
    if agent.archived_at is None:
        raise AgentNotArchivedError
    if confirm_name != agent.name:
        raise AgentNameMismatchError
    conversations = await session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.agent_id == agent.id)
    )
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=DELETED,
        target=audit.AuditTarget("agent", agent.id),
        before={
            "name": agent.name,
            "project_id": str(agent.project_id),
            "public_id": agent.public_id,
            "conversation_count": conversations,
        },
        occurred_at=now,
    )
    await session.execute(delete(Agent).where(Agent.id == agent.id))
    await session.commit()


async def save_draft(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    config: AgentConfig,
    *,
    now: datetime,
) -> AgentWithDraft:
    """Replaces the Agent's Draft with ``config``, once ``check_draft`` finds no problem (it
    raises ``InvalidDraftError``). The credentials it names become Credential references."""
    project = await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id)
    await check_draft(session, scope, project, config)
    draft = await session.get_one(AgentDraft, found.agent.id, with_for_update=True)
    draft.config = config.model_dump(mode="json")
    draft.updated_at = now
    await session.commit()
    return AgentWithDraft(found.agent, config, now)
