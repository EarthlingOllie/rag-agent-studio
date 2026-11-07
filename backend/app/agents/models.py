"""Agents and their Drafts. An Agent carries its Organisation and Project (ADR-0001)."""

import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin

NAME_MAX = 200
PUBLIC_ID_PREFIX = "agt_"
ORIGIN_MAX = 255
UNAVAILABLE_TEXT_MAX = 500


def new_public_id() -> str:
    """An unguessable ID the embed (spec 06) addresses the Agent by."""
    return PUBLIC_ID_PREFIX + secrets.token_urlsafe(18)


class Agent(IdMixin, Base):
    __tablename__ = "agents"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    public_id: Mapped[str] = mapped_column(String(64), unique=True, default=new_public_id)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Live Version: what Visitors are served. None until the Agent is first published, so
    # the Agent is not live.
    live_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id", name="fk_agents_live_version", use_alter=True)
    )
    # Operational Settings: not part of any Draft or Version, and applied on the next request.
    # The sites (scheme, host or subdomain wildcard, and optional port) whose pages may frame
    # the Agent's widget: the shell's ``frame-ancestors`` policy. Empty means none may.
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(String(ORIGIN_MAX)), server_default=text("'{}'")
    )
    # What Visitors are told when the Agent can't answer; None means the platform's default.
    unavailable_text: Mapped[str | None] = mapped_column(String(UNAVAILABLE_TEXT_MAX))


class AgentDraft(Base):
    """The Agent's one editable configuration. Publishing it makes an ``AgentVersion``."""

    __tablename__ = "agent_drafts"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), primary_key=True
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    # An ``AgentConfig`` as JSON; read it through ``AgentConfig.model_validate``.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 1, 2, 3…: moves on with every change of the Draft. A change names the revision it was
    # made on, and is refused when the Draft has moved on since (optimistic concurrency).
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class AgentVersion(IdMixin, Base):
    """An immutable, numbered snapshot of an Agent's Draft, pinning the Project Instructions
    Version it runs with. Migration ``0026_agent_versions`` adds a trigger that refuses every
    UPDATE; rows go only with their Agent."""

    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "number"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Agent.id, ondelete="CASCADE"))
    # 1, 2, 3… per Agent, allocated under the Agent's row lock.
    number: Mapped[int] = mapped_column(Integer)
    # The Draft's ``AgentConfig`` as JSON when it was published.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The Project Instructions Version it runs with; None when the Project had no Instructions
    # Version, so it runs with no Project Instructions.
    instructions_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "project_instructions_versions.id", name="fk_agent_versions_instructions_version"
        )
    )
    note: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"))


class LiveHistoryEntry(IdMixin, Base):
    """One change of an Agent's Live Version: append-only, like the Versions (the same
    migration's trigger refuses every UPDATE)."""

    __tablename__ = "agent_live_history"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    # Orders an Agent's entries as they were written (under the Agent's row lock), even when
    # two share a timestamp.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    # The Live Version before; None for the first publish.
    from_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(AgentVersion.id))
    to_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(AgentVersion.id))
    # publish, revert, bulk_publish or bulk_revert.
    action: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set when a bulk action made the change (05-05).
    bulk_operation_id: Mapped[uuid.UUID | None]
