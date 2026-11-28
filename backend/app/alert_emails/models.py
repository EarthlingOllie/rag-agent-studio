"""One alert email to one Owner: when its alert was raised and when it was sent."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent
from app.core.db import Base, IdMixin
from app.tenancy.models import Member, Organisation


class Alert(StrEnum):
    TOKEN_BUDGET_EXHAUSTED = "token_budget_exhausted"  # noqa: S105 (an alert, not a password)
    EVALUATION_BUDGET_SPENT = "evaluation_budget_spent"
    BLOCK_RATE = "block_rate"
    LIVE_SCORE_DROP = "live_score_drop"


class AlertEmail(IdMixin, Base):
    """The email one Owner is sent when an alert is raised, rendered for them in the
    transaction that raised it. ``sent_at`` is set once it has been sent; until then the
    sweeper sends it."""

    __tablename__ = "alert_emails"
    __table_args__ = (
        Index("ix_alert_emails_unsent", "raised_at", postgresql_where=text("sent_at IS NULL")),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    # The Agent the alert is about; None for the Evaluation budget, which is the Organisation's.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    # An ``Alert``.
    alert: Mapped[str] = mapped_column(String(30))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The Owner, and the email rendered for them.
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Member.id, ondelete="CASCADE"), index=True
    )
    to: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
