"""Creating, listing and reading a Project's Agents, saving an Agent's Draft, and archiving,
restoring and permanently deleting an Agent.

Every function takes an ``OrganisationScope`` and a Project ID, so an Agent is only found inside
its own Project of the Organisation the Member works in. Changes go through
``active_project``, so an archived Project's Agents can't be created or changed; an archived
Agent's Draft can't be changed either, and it starts no Playground Conversation.

Every change of a Draft moves it to its next revision. A change may name the revision it was
made on (``base_revision``); when the Draft has moved on since, it is refused with
``StaleDraftError`` carrying the latest Draft, so nobody silently overwrites a colleague's
edits. ``replace_draft`` applies that rule for saving, discarding and starting from a Version.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentDraft, AgentVersion
from app.agents.validation import check_draft
from app.conversations.models import Conversation
from app.projects.models import Project
from app.projects.service import active_project, get_project
from app.tenancy.repository import OrganisationScope

CREATED = "agent.created"
ARCHIVED = "agent.archived"
RESTORED = "agent.restored"
DELETED = "agent.deleted"
RETRIEVAL_MODE_CHANGED = "agent.retrieval_mode_changed"

# The Retrieval settings a Draft change is audited for, with the names the Audit Event gives them.
_AUDITED_RETRIEVAL = (("mode", "retrieval_mode"), ("search_limit", "search_limit"))
DRAFT_SETTINGS_CHANGED = "agent.draft_settings_changed"
# The Draft settings that decide which provider, through which Provider Credential, sees the
# conversation, how injections are judged, and what image Visitors load; by group and key, with
# the name the Audit Event gives each.
_AUDITED_SETTINGS = (
    ("behaviour", "model", "model"),
    ("retrieval", "reranker", "reranker"),
    ("guardrails", "classifier", "guardrail_classifier"),
    ("guardrails", "fail_mode", "guardrail_fail_mode"),
    ("experience", "avatar_url", "avatar_url"),
)


class AgentNotFoundError(Exception):
    """No Agent with that ID in the Project."""


class AgentArchivedError(Exception):
    """The Agent is archived, so it can't be changed or used until an Owner restores it."""


class AgentNotArchivedError(Exception):
    """Only an archived Agent can be restored or permanently deleted."""


class AgentNameMismatchError(Exception):
    """The name typed to confirm a permanent deletion isn't the Agent's name."""


@dataclass(frozen=True)
class LiveVersion:
    id: uuid.UUID
    number: int


@dataclass(frozen=True)
class AgentWithDraft:
    agent: Agent
    draft: AgentConfig
    draft_updated_at: datetime
    draft_revision: int
    # None while the Agent has never been published, so it is not live.
    live_version: LiveVersion | None
    # Whether the Draft differs from the Live Version's configuration; False while not live.
    has_unpublished_changes: bool


class StaleDraftError(Exception):
    """The Draft has moved on since the revision the change was made on."""

    def __init__(self, latest: AgentWithDraft) -> None:
        self.latest = latest


async def with_draft(session: AsyncSession, agent: Agent) -> AgentWithDraft:
    """The Agent with its Draft, its revision and its Live Version."""
    draft = await session.get_one(AgentDraft, agent.id)
    config = AgentConfig.model_validate(draft.config)
    live = None
    changed = False
    if agent.live_version_id is not None:
        version = await session.get_one(AgentVersion, agent.live_version_id)
        live = LiveVersion(version.id, version.number)
        changed = AgentConfig.model_validate(version.config) != config
    return AgentWithDraft(agent, config, draft.updated_at, draft.revision, live, changed)


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
    return await with_draft(session, agent)


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
    return [await with_draft(session, agent) for agent in agents]


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
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    lock: bool = False,
) -> AgentWithDraft:
    """The Agent, archived or not; with ``lock`` its row is locked until the transaction
    ends."""
    return await with_draft(session, await _find(session, scope, project_id, agent_id, lock=lock))


async def active_agent(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    lock: bool = False,
) -> AgentWithDraft:
    """The Agent, refused with ``AgentArchivedError`` while it is archived."""
    found = await get_agent(session, scope, project_id, agent_id, lock=lock)
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
    return await with_draft(session, agent)


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


async def _audit_settings(
    session: AsyncSession,
    scope: OrganisationScope,
    agent: Agent,
    before: AgentConfig,
    after: AgentConfig,
    now: datetime,
) -> None:
    """Records ``agent.draft_settings_changed`` when a Draft change moves the model, the
    reranker, the Guardrail classifier or fail mode, or the avatar URL, with the before and
    after values of just the settings that changed (Provider Credentials by ID)."""
    old, new = before.model_dump(mode="json"), after.model_dump(mode="json")
    changed = [
        (group, key, name)
        for group, key, name in _AUDITED_SETTINGS
        if old[group][key] != new[group][key]
    ]
    if not changed:
        return
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=DRAFT_SETTINGS_CHANGED,
        target=audit.AuditTarget("agent", agent.id),
        before={name: old[group][key] for group, key, name in changed},
        after={name: new[group][key] for group, key, name in changed},
        occurred_at=now,
    )


async def _audit_retrieval_mode(
    session: AsyncSession,
    scope: OrganisationScope,
    agent: Agent,
    before: AgentConfig,
    after: AgentConfig,
    now: datetime,
) -> None:
    """Records ``agent.retrieval_mode_changed`` when a Draft change moves the Retrieval Mode or
    the Search limit, with the before and after values of just the settings that changed."""
    old, new = before.retrieval.model_dump(mode="json"), after.retrieval.model_dump(mode="json")
    changed = [(key, name) for key, name in _AUDITED_RETRIEVAL if old[key] != new[key]]
    if not changed:
        return
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=RETRIEVAL_MODE_CHANGED,
        target=audit.AuditTarget("agent", agent.id),
        before={name: old[key] for key, name in changed},
        after={name: new[key] for key, name in changed},
        occurred_at=now,
    )


async def replace_draft(
    session: AsyncSession,
    scope: OrganisationScope,
    project: Project,
    agent: Agent,
    config: AgentConfig,
    *,
    base_revision: int | None,
    now: datetime,
) -> AgentDraft:
    """Replaces the active ``agent``'s Draft with ``config`` and moves it to its next revision,
    in the caller's transaction. Refused with ``StaleDraftError`` when ``base_revision`` is
    given and the Draft has moved on from it, then with ``InvalidDraftError`` when
    ``check_draft`` finds a problem. The credentials it names become Credential references."""
    draft = await session.get_one(AgentDraft, agent.id, with_for_update=True)
    if base_revision is not None and base_revision != draft.revision:
        raise StaleDraftError(await with_draft(session, agent))
    await check_draft(session, scope, project, config)
    previous = AgentConfig.model_validate(draft.config)
    await _audit_retrieval_mode(session, scope, agent, previous, config, now)
    await _audit_settings(session, scope, agent, previous, config, now)
    draft.config = config.model_dump(mode="json")
    draft.updated_at = now
    draft.revision += 1
    return draft


async def save_draft(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    config: AgentConfig,
    *,
    base_revision: int | None = None,
    now: datetime,
) -> AgentWithDraft:
    """Replaces the Agent's Draft with ``config`` (see ``replace_draft``)."""
    project = await active_project(session, scope, project_id)
    agent = (await active_agent(session, scope, project_id, agent_id)).agent
    await replace_draft(
        session, scope, project, agent, config, base_revision=base_revision, now=now
    )
    await session.commit()
    return await with_draft(session, agent)
