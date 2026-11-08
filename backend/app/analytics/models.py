"""The ``usage_daily`` rollups: per Agent Version per UTC day, the counts and sums the Version
KPIs are read from, with fixed-bucket histograms (``app.analytics.stats.Histogram``, stored as
``{bucket: count}``) for percentiles. Only Visitor Conversations count: Playground ones never do.

``usage_rollup_state`` records, per Organisation, the last day whose rollup is final (the day
is over, and its rollup will not be recomputed by the hourly task)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class UsageDaily(IdMixin, Base):
    __tablename__ = "usage_daily"
    __table_args__ = (UniqueConstraint("agent_version_id", "day"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="CASCADE")
    )
    # The UTC day.
    day: Mapped[date] = mapped_column(Date, index=True)
    # Visitor Conversations whose first reply from this Version came this day.
    conversations: Mapped[int] = mapped_column(Integer)
    # The Version's replies (Agent Messages) this day.
    messages: Mapped[int] = mapped_column(Integer)
    # Replies that asked a model (not fallback replies or refusals): their count, the sum of
    # their input and output tokens, and a histogram of tokens per reply.
    token_replies: Mapped[int] = mapped_column(Integer)
    tokens: Mapped[int] = mapped_column(BigInteger)
    tokens_histogram: Mapped[dict[str, int]] = mapped_column(JSONB)
    # The sum of the replies' frozen costs, in US dollars (replies with no known price add 0).
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9))
    # Message Feedback on this day's replies.
    thumbs_up: Mapped[int] = mapped_column(Integer)
    thumbs_down: Mapped[int] = mapped_column(Integer)
    # Conversation Ratings attributed to this Version, of Conversations started this day.
    rating_sum: Mapped[int] = mapped_column(Integer)
    rating_count: Mapped[int] = mapped_column(Integer)
    # Fallback replies.
    fallback_count: Mapped[int] = mapped_column(Integer)
    # Replies that were the refusal text because the input Guardrail blocked the question.
    guardrail_blocks: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Histograms of milliseconds to the first token, and to the whole reply.
    first_token_histogram: Mapped[dict[str, int]] = mapped_column(JSONB)
    latency_histogram: Mapped[dict[str, int]] = mapped_column(JSONB)


class UsageRollupState(Base):
    """How far an Organisation's rollups are final: every day up to and including
    ``finalised_through`` has been finalised and is not recomputed by the hourly task."""

    __tablename__ = "usage_rollup_state"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    finalised_through: Mapped[date] = mapped_column(Date)
    finalised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
