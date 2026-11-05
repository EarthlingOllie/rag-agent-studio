"""Agents and their Drafts. An Agent carries its Organisation and Project (ADR-0001)."""

import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin

NAME_MAX = 200
PUBLIC_ID_PREFIX = "agt_"


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


class AgentDraft(Base):
    """The Agent's one editable configuration. Versions arrive in spec 05."""

    __tablename__ = "agent_drafts"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), primary_key=True
    )
    # An ``AgentConfig`` as JSON; read it through ``AgentConfig.model_validate``.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
