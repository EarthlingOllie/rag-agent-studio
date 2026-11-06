"""Agent Versions: publishing an Agent's Draft as its Live Version, the Version list, the Live
History, and what a Visitor is served.

An Agent has one editable Draft, an append-only list of immutable, numbered Versions, and a
Live Version pointer, which is None until the first publish (the Agent is then "not live").

- **Publish** freezes the Draft into the next Version (1, 2, 3… per Agent). Each Version pins a
  Project Instructions Version: the Project's Current Version by default, or one the Editor
  chooses; with no Instructions Version in the Project it pins none and runs with no Project
  Instructions. The Agent row is locked (``SELECT … FOR UPDATE``) and the number allocated
  inside the lock, so concurrent publishes get consecutive, unique numbers. The new Version
  becomes the Live Version, a Live History entry records the move (from-Version, to-Version,
  ``publish``, actor, time), and ``agent.published`` is audited, all in one transaction.
- **Revert** moves the Live Version back one step in the Agent's **Live History**, restoring
  the configuration and the pinned Instructions it ran with. The rule: the target is the
  from-Version of the entry that moved Live onto the current Live Version by a *publish* (or
  bulk publish). Revert entries are not followed, so publish → revert → revert walks further
  back instead of toggling between two Versions. This works as a stack: every publish pushes a
  new Version (each Version is pushed exactly once, when it's created) and every revert pops
  one. For example, with v1, v2, v3 published in turn, revert gives v2 then v1; and after
  v1, v2, revert (v1), publish v3, revert gives v1, skipping v2, which was already reverted.
  When that entry has no from-Version (the first publish) or the Agent is not live, there is
  nothing to revert to and the revert is refused. The Agent row is locked as for publish, the
  move is written to the Live History as ``revert``, and ``agent.reverted`` is audited. The
  Draft is left alone. A Version whose credentials have since been deleted can't be made Live
  again.
- **Bulk publish and bulk revert** (``app.agents.bulk``) make the same moves through
  ``make_live`` and ``step_back``, one Agent per transaction, writing ``bulk_publish`` or
  ``bulk_revert`` entries and ``agent.bulk_published`` or ``agent.bulk_reverted`` events that
  carry the bulk operation ID.
- **Versions are immutable.** No route changes or deletes one, and migration
  ``0026_agent_versions`` adds a trigger refusing every UPDATE to Versions and Live History
  entries. They go only with their Agent.
- **Serving.** ``served`` resolves what a Visitor gets: the Live Version's AgentConfig and its
  pinned Instructions text. Messages it answers record the Version (``config_source`` is
  ``version``); Playground answers record the Draft marker and no Version.

Every operation goes through the Project and Agent lookups, so another Organisation's Agent is
"not found", and an archived Project or Agent can't be published.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import audit
from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentDraft, AgentVersion, LiveHistoryEntry
from app.agents.service import active_agent, get_agent
from app.agents.validation import DraftProblem, credential_problems
from app.projects.models import InstructionsVersion
from app.projects.service import active_project
from app.tenancy.models import Member
from app.tenancy.repository import OrganisationScope

PUBLISHED = "agent.published"
REVERTED = "agent.reverted"
BULK_PUBLISHED = "agent.bulk_published"
BULK_REVERTED = "agent.bulk_reverted"
PUBLISH = "publish"
REVERT = "revert"
BULK_PUBLISH = "bulk_publish"
BULK_REVERT = "bulk_revert"
# The Live History actions that put a new Version Live; reverts follow these back.
_PUSHES = (PUBLISH, BULK_PUBLISH)
_AUDIT_ACTIONS = {
    PUBLISH: PUBLISHED,
    REVERT: REVERTED,
    BULK_PUBLISH: BULK_PUBLISHED,
    BULK_REVERT: BULK_REVERTED,
}


NOTHING_TO_REVERT = "There's no earlier Live Version to revert to."
REVERT_TARGET_INVALID = (
    "The Version that was Live before uses a Provider Credential or model that is no longer "
    "available, so it can't be made Live again. Publish a fixed Version instead."
)


class InstructionsVersionNotFoundError(Exception):
    """The chosen Instructions Version isn't one of the Agent's Project's."""


class AgentVersionNotFoundError(Exception):
    """No Version with that ID for the Agent."""


class NothingToRevertError(Exception):
    """The Agent is not live, or its Live Version was its first."""


class RevertTargetInvalidError(Exception):
    """The Version a revert would make Live names something that no longer exists."""

    def __init__(self, problems: list[DraftProblem]) -> None:
        self.problems = problems


@dataclass(frozen=True)
class Person:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class PinnedInstructions:
    id: uuid.UUID
    number: int


@dataclass(frozen=True)
class VersionView:
    version: AgentVersion
    config: AgentConfig
    author: Person
    instructions: PinnedInstructions | None


@dataclass(frozen=True)
class VersionList:
    live_version_id: uuid.UUID | None
    # Newest first.
    versions: list[VersionView]


@dataclass(frozen=True)
class VersionNumber:
    id: uuid.UUID
    number: int


@dataclass(frozen=True)
class LiveHistoryView:
    entry: LiveHistoryEntry
    from_version: VersionNumber | None
    to_version: VersionNumber
    actor: Person


async def _view(session: AsyncSession, version: AgentVersion) -> VersionView:
    name = await session.scalar(select(Member.name).where(Member.id == version.author_id))
    pinned = None
    if version.instructions_version_id is not None:
        found = await session.get_one(InstructionsVersion, version.instructions_version_id)
        pinned = PinnedInstructions(found.id, found.number)
    return VersionView(
        version,
        AgentConfig.model_validate(version.config),
        Person(version.author_id, name or ""),
        pinned,
    )


def _summary(version: AgentVersion | None) -> dict[str, object] | None:
    if version is None:
        return None
    return {"version_id": str(version.id), "number": version.number}


async def publish(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    note: str,
    *,
    instructions_version_id: uuid.UUID | None = None,
    now: datetime,
) -> VersionView:
    """Freezes the Draft into the next Version, pinning ``instructions_version_id`` or else the
    Project's Current Instructions Version, and makes it the Live Version."""
    project = await active_project(session, scope, project_id)
    # Lock the Agent row: publishes of one Agent queue here, so numbers never collide.
    found = await active_agent(session, scope, project_id, agent_id, lock=True)
    pinned_id = project.current_instructions_version_id
    if instructions_version_id is not None:
        pinned_id = await project_instructions_version(session, project.id, instructions_version_id)
    draft = await session.get_one(AgentDraft, found.agent.id)
    view = await make_live(
        session, scope, found.agent, draft.config, pinned_id, note, Move(PUBLISH), now=now
    )
    await session.commit()
    return view


async def project_instructions_version(
    session: AsyncSession, project_id: uuid.UUID, version_id: uuid.UUID
) -> uuid.UUID:
    """``version_id`` when it is one of the Project's Instructions Versions."""
    found = await session.scalar(
        select(InstructionsVersion.id).where(
            InstructionsVersion.id == version_id, InstructionsVersion.project_id == project_id
        )
    )
    if found is None:
        raise InstructionsVersionNotFoundError
    return found


@dataclass(frozen=True)
class Move:
    """How the Live Version moves: the Live History action and, for a bulk action, its ID."""

    action: str
    bulk_operation_id: uuid.UUID | None = None

    @property
    def audit_action(self) -> str:
        return _AUDIT_ACTIONS[self.action]

    def audited(self, after: dict[str, object]) -> dict[str, object]:
        if self.bulk_operation_id is None:
            return after
        return {**after, "bulk_operation_id": str(self.bulk_operation_id)}


async def make_live(
    session: AsyncSession,
    scope: OrganisationScope,
    agent: Agent,
    config: dict[str, Any],
    pinned_id: uuid.UUID | None,
    note: str,
    move: Move,
    *,
    now: datetime,
) -> VersionView:
    """Adds the Agent's next Version (``config`` pinning ``pinned_id``) and makes it Live,
    writing the Live History entry and the Audit Event. The caller holds the Agent row lock and
    commits."""
    latest = await session.scalar(
        select(func.max(AgentVersion.number)).where(AgentVersion.agent_id == agent.id)
    )
    previous = await _version(session, agent.live_version_id)
    version = AgentVersion(
        organisation_id=scope.organisation_id,
        agent_id=agent.id,
        number=(latest or 0) + 1,
        config=config,
        instructions_version_id=pinned_id,
        note=note,
        author_id=scope.member_id,
        created_at=now,
    )
    session.add(version)
    await session.flush()
    agent.live_version_id = version.id
    _write_history(session, scope, agent, previous, version, move, now)
    view = await _view(session, version)
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=move.audit_action,
        target=audit.AuditTarget("agent", agent.id),
        before={"live_version": _summary(previous)},
        after=move.audited(
            {"live_version": {**(_summary(version) or {}), "note": note, **_pinned(view)}}
        ),
        occurred_at=now,
    )
    return view


def _write_history(
    session: AsyncSession,
    scope: OrganisationScope,
    agent: Agent,
    previous: AgentVersion | None,
    version: AgentVersion,
    move: Move,
    now: datetime,
) -> None:
    session.add(
        LiveHistoryEntry(
            organisation_id=scope.organisation_id,
            agent_id=agent.id,
            from_version_id=previous and previous.id,
            to_version_id=version.id,
            action=move.action,
            actor_id=scope.member_id,
            occurred_at=now,
            bulk_operation_id=move.bulk_operation_id,
        )
    )


async def revert(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> VersionView:
    """Moves the Live Version back one step in the Live History (see the module docstring for
    the rule) and returns the Version that is Live again."""
    await active_project(session, scope, project_id)
    agent = (await active_agent(session, scope, project_id, agent_id, lock=True)).agent
    view = await step_back(session, scope, agent, Move(REVERT), now=now)
    await session.commit()
    return view


async def step_back(
    session: AsyncSession, scope: OrganisationScope, agent: Agent, move: Move, *, now: datetime
) -> VersionView:
    """Moves the Agent's Live Version back by the revert rule, writing the Live History entry
    and the Audit Event. The caller holds the Agent row lock and commits."""
    current = await _version(session, agent.live_version_id)
    target = None
    if current is not None:
        target_id = await session.scalar(
            select(LiveHistoryEntry.from_version_id)
            .where(
                LiveHistoryEntry.agent_id == agent.id,
                LiveHistoryEntry.to_version_id == current.id,
                LiveHistoryEntry.action.in_(_PUSHES),
            )
            .order_by(LiveHistoryEntry.seq.desc())
            .limit(1)
        )
        target = await _version(session, target_id)
    if current is None or target is None:
        raise NothingToRevertError
    problems = await credential_problems(session, scope, AgentConfig.model_validate(target.config))
    if problems:
        raise RevertTargetInvalidError(problems)
    agent.live_version_id = target.id
    _write_history(session, scope, agent, current, target, move, now)
    view = await _view(session, target)
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=move.audit_action,
        target=audit.AuditTarget("agent", agent.id),
        before={"live_version": _summary(current)},
        after=move.audited({"live_version": {**(_summary(target) or {}), **_pinned(view)}}),
        occurred_at=now,
    )
    return view


def _pinned(view: VersionView) -> dict[str, object]:
    pinned = view.instructions
    return {
        "instructions_version": pinned and {"version_id": str(pinned.id), "number": pinned.number}
    }


async def _version(session: AsyncSession, version_id: uuid.UUID | None) -> AgentVersion | None:
    return None if version_id is None else await session.get(AgentVersion, version_id)


async def list_versions(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> VersionList:
    """The Agent's Versions, newest first, and which is Live. Archived Agents can be read."""
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    versions = await session.scalars(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.number.desc())
    )
    return VersionList(agent.live_version_id, [await _view(session, v) for v in versions])


async def get_version(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
) -> VersionView:
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    version = await session.scalar(
        select(AgentVersion).where(AgentVersion.id == version_id, AgentVersion.agent_id == agent.id)
    )
    if version is None:
        raise AgentVersionNotFoundError
    return await _view(session, version)


async def live_history(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> list[LiveHistoryView]:
    """Every change of the Agent's Live Version, newest first."""
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    source = aliased(AgentVersion)
    target = aliased(AgentVersion)
    rows = await session.execute(
        select(LiveHistoryEntry, source, target, Member.name)
        .outerjoin(source, source.id == LiveHistoryEntry.from_version_id)
        .join(target, target.id == LiveHistoryEntry.to_version_id)
        .join(Member, Member.id == LiveHistoryEntry.actor_id)
        .where(LiveHistoryEntry.agent_id == agent.id)
        .order_by(LiveHistoryEntry.seq.desc())
    )
    return [
        LiveHistoryView(
            entry,
            None if from_version is None else VersionNumber(from_version.id, from_version.number),
            VersionNumber(to_version.id, to_version.number),
            Person(entry.actor_id, name),
        )
        for entry, from_version, to_version, name in rows
    ]


@dataclass(frozen=True)
class Served:
    """What a Visitor is served: the Live Version's configuration and pinned Instructions."""

    agent_version_id: uuid.UUID
    config: AgentConfig
    instructions: str


async def served(session: AsyncSession, agent: Agent) -> Served | None:
    """The Agent's Live Version as the runtime runs it, or None while the Agent is not live."""
    version = await _version(session, agent.live_version_id)
    if version is None:
        return None
    pinned = await _version_instructions(session, version.instructions_version_id)
    return Served(version.id, AgentConfig.model_validate(version.config), pinned)


async def _version_instructions(session: AsyncSession, version_id: uuid.UUID | None) -> str:
    if version_id is None:
        return ""
    return (await session.get_one(InstructionsVersion, version_id)).markdown
