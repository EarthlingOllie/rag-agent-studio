"""An Agent's Theme override: colour tokens that replace the Organisation Theme's in the Agent's
widget, and an avatar. Owners change it, as they change the Theme; every Member can view it.
It is an Operational Setting, not part of AgentConfig (ADR-0009): it isn't versioned, and a
change applies to the next widget shell without publishing. Each change records
``agent.theme_override_updated`` with only what changed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.models import Agent
from app.agents.service import get_agent
from app.storage.port import ObjectStore
from app.tenancy.repository import OrganisationScope
from app.theme import images
from app.theme.images import PendingUpload
from app.theme.schema import ColourToken, HexColour
from app.theme.service import StoredImage

TokenName = Literal["primary", "on_primary", "surface", "on_surface", "accent", "muted"]


class OverrideColour(BaseModel):
    """A colour token's light-mode and dark-mode value for one Agent."""

    model_config = ConfigDict(extra="forbid")

    light: HexColour
    dark: HexColour


class ColourOverride(BaseModel):
    """The colour tokens an Agent overrides; the rest follow the Organisation's Theme."""

    model_config = ConfigDict(extra="forbid")

    colours: dict[TokenName, OverrideColour]


@dataclass(frozen=True)
class ThemeOverride:
    colours: dict[str, ColourToken]
    avatar: StoredImage | None


def override_of(agent: Agent) -> ThemeOverride:
    colours = {token: ColourToken(**value) for token, value in agent.theme_colours.items()}
    avatar = None if agent.avatar is None else StoredImage.from_stored(agent.avatar)
    return ThemeOverride(colours, avatar)


async def read_override(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> ThemeOverride:
    return override_of((await get_agent(session, scope, project_id, agent_id)).agent)


async def _record(
    session: AsyncSession,
    scope: OrganisationScope,
    agent: Agent,
    before: dict[str, Any],
    after: dict[str, Any],
    now: datetime,
) -> None:
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="agent.theme_override_updated",
        target=audit.AuditTarget("agent", agent.id),
        before=before,
        after=after,
        occurred_at=now,
    )


async def set_colours(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    override: ColourOverride,
    *,
    now: datetime,
) -> ThemeOverride:
    """Replaces the Agent's overridden colours; an empty map follows the Theme again."""
    agent = (await get_agent(session, scope, project_id, agent_id, lock=True)).agent
    colours = override.model_dump(mode="json")["colours"]
    if colours != agent.theme_colours:
        await _record(
            session, scope, agent, {"colours": agent.theme_colours}, {"colours": colours}, now
        )
        agent.theme_colours = colours
    await session.commit()
    return override_of(agent)


def _pending_key(agent_id: uuid.UUID, upload_id: uuid.UUID) -> str:
    return f"agent-avatar-upload:{agent_id}:{upload_id}"


async def start_avatar_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    filename: str,
    size_bytes: int,
    max_bytes: int,
    ttl_seconds: int,
    now: datetime,
) -> PendingUpload:
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    return await images.start_image_upload(
        redis,
        store,
        pending_key=lambda upload_id: _pending_key(agent.id, upload_id),
        object_prefix=f"organisations/{scope.organisation_id}/agents/{agent.id}/avatar",
        filename=filename,
        size_bytes=size_bytes,
        max_bytes=max_bytes,
        ttl_seconds=ttl_seconds,
        now=now,
    )


async def _set_avatar(
    session: AsyncSession,
    store: ObjectStore,
    scope: OrganisationScope,
    agent: Agent,
    image: StoredImage | None,
    now: datetime,
) -> ThemeOverride:
    previous = override_of(agent).avatar
    if previous is None and image is None:
        await session.commit()
        return override_of(agent)
    agent.avatar = None if image is None else image.stored()
    await _record(
        session,
        scope,
        agent,
        {"avatar": None if previous is None else previous.audited()},
        {"avatar": None if image is None else image.audited()},
        now,
    )
    await session.commit()
    if previous is not None:
        await store.delete(previous.object_key)
    return override_of(agent)


async def confirm_avatar_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    upload_id: uuid.UUID,
    max_bytes: int,
    now: datetime,
) -> ThemeOverride:
    """Checks the uploaded image and makes it the Agent's avatar, deleting the one it had."""
    agent = (await get_agent(session, scope, project_id, agent_id, lock=True)).agent
    image = await images.claim_upload(
        redis, store, _pending_key(agent.id, upload_id), max_bytes=max_bytes, now=now
    )
    return await _set_avatar(session, store, scope, agent, image, now)


async def remove_avatar(
    session: AsyncSession,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> ThemeOverride:
    """Removes the Agent's avatar, so the widget shows the Live Version's or the Theme's."""
    agent = (await get_agent(session, scope, project_id, agent_id, lock=True)).agent
    return await _set_avatar(session, store, scope, agent, None, now)
