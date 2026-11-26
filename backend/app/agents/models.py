"""Agents and their Drafts. An Agent carries its Organisation and Project (ADR-0001)."""

import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
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
# Rate limits: Visitor messages admitted in any one minute.
CONVERSATION_RATE_DEFAULT = 10
CONVERSATION_RATE_MAX = 1000
IP_RATE_DEFAULT = 30
IP_RATE_MAX = 10000
# The Token Budget: tokens an Agent's Visitor replies may use in one UTC day.
TOKEN_BUDGET_DEFAULT = 1_000_000
TOKEN_BUDGET_MAX = 1_000_000_000
# The Live sample rate: the whole percentage of Visitor replies judged (spec 15).
LIVE_SAMPLE_RATE_MAX = 100
# The Call settings (spec 20).
SPOKEN_GREETING_MAX = 500
VOICE_ID_MAX = 64
# The Call limits (spec 20): how long one Call may last, and the minutes of Calls an Agent's
# Visitors may use per UTC date.
MAX_CALL_MINUTES_DEFAULT = 10
MAX_CALL_MINUTES_MAX = 60
CALL_MINUTES_BUDGET_DEFAULT = 60
CALL_MINUTES_BUDGET_MAX = 1_000_000


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
    # Rate limits: how many Visitor messages are admitted in any minute (a sliding window) for
    # one Conversation, and for one IP address.
    conversation_messages_per_minute: Mapped[int] = mapped_column(
        Integer, server_default=text(str(CONVERSATION_RATE_DEFAULT))
    )
    ip_messages_per_minute: Mapped[int] = mapped_column(
        Integer, server_default=text(str(IP_RATE_DEFAULT))
    )
    # The Token Budget: how many tokens Visitor replies may use per UTC date. The day's usage is
    # counted in Redis (admission control); the Playground doesn't count.
    daily_token_budget: Mapped[int] = mapped_column(
        Integer, server_default=text(str(TOKEN_BUDGET_DEFAULT))
    )
    # The Live sample rate: the chance, in whole percent, that a Visitor reply is chosen for a
    # Live Verdict (``app.evaluation.live``). 0, the default, judges nothing.
    live_sample_rate: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # The budget alert flag: when the day's Token Budget ran out, shown as the Studio's alert
    # badge. Beat clears it at midnight UTC; None when there is no alert.
    budget_exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Block rate alert flag: when the hourly rollup found the input Guardrail's block rate
    # spiking, shown as the Studio's alert badge. The first run that finds no spike clears it;
    # None when there is no alert.
    block_rate_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Live score drop alert flag: when the hourly check found the Live Version's Live score
    # clearly lower than the previous Live Version's (``app.analytics.alerts``), shown as the
    # Studio's alert badge, and the Live Version it was raised against. A run that no longer
    # finds the drop clears both, and so does any change of the Live Version; None when there
    # is no alert.
    live_score_drop_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    live_score_drop_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id", name="fk_agents_live_score_drop_version", use_alter=True)
    )
    # The Call settings: whether the Agent takes Calls (off by default), the voice-capable
    # Provider Credential and the voice it speaks with, and the spoken greeting that opens a
    # Call. The credential is a Credential reference while calling is on.
    calls_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    call_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_credentials.id", ondelete="SET NULL"), index=True
    )
    call_voice_id: Mapped[str | None] = mapped_column(String(VOICE_ID_MAX))
    spoken_greeting: Mapped[str] = mapped_column(
        String(SPOKEN_GREETING_MAX), server_default=text("''")
    )
    # The Agent's remote agent in the voice layer (``app.voice``), while calling is on, and
    # the per-Agent secret it presents to our turn endpoint, sealed with envelope encryption.
    remote_agent_id: Mapped[str | None] = mapped_column(String(128))
    call_secret_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    # The Call limits: the Maximum Call length in minutes, and the Call minutes budget, the
    # minutes of Calls its Visitors may use per UTC date (counted in ``call_minutes_used``).
    max_call_minutes: Mapped[int] = mapped_column(
        Integer, server_default=text(str(MAX_CALL_MINUTES_DEFAULT))
    )
    call_minutes_budget: Mapped[int] = mapped_column(
        Integer, server_default=text(str(CALL_MINUTES_BUDGET_DEFAULT))
    )
    # The Call minutes budget's alert flag: when a Call was first refused because the day's
    # Call minutes were spent. Beat clears it at midnight UTC; None when there is no alert.
    call_budget_exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Calls failing alert flag: when the voice layer couldn't start one of the Agent's Calls
    # (its remote agent gone, the key revoked, the provider unreachable). Saving the Call
    # settings, which sets the remote agent up again, or the next Call that starts clears it;
    # None when there is no alert.
    calls_failing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Theme override, set by Owners and not versioned: colour tokens replacing the
    # Organisation Theme's ({token: {"light", "dark"}}, only those overridden) and an avatar
    # image (stored as the Theme's images are), or None.
    theme_colours: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    avatar: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


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
