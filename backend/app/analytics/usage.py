"""One UTC day's usage per Agent Version, worked out from the raw tables: the numbers a
``usage_daily`` row holds. The rollup task stores them; the Version metrics query works the
current (partial) day out the same way.

Only Visitor Conversations count: Playground Conversations (and Draft answers) never do. Each
number belongs to a day by a time that doesn't move once it exists:
- replies, their tokens, cost, latency, fallbacks and Guardrail blocks: when the reply was made;
- Message Feedback: when the reply it is on was made;
- a Conversation: when this Version first replied in it (so it counts once per Version);
- a Conversation Rating: when the Conversation's first reply was made.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.analytics.models import UsageDaily, UsageRollupState
from app.analytics.stats import Histogram
from app.conversations.models import Conversation, Message, MessageRole
from app.feedback.models import ConversationRating, MessageFeedback, Thumb
from app.guardrails.outcomes import blocked

DOLLARS = Decimal("0.000000001")


@dataclass
class Usage:
    """An Agent Version's usage over one day or several: counts, sums and histograms that add
    up across days."""

    conversations: int = 0
    messages: int = 0
    token_replies: int = 0
    tokens: int = 0
    tokens_histogram: Histogram = field(default_factory=Histogram)
    cost_usd: Decimal = Decimal(0)
    thumbs_up: int = 0
    thumbs_down: int = 0
    rating_sum: int = 0
    rating_count: int = 0
    fallback_count: int = 0
    guardrail_blocks: int = 0
    first_token_histogram: Histogram = field(default_factory=Histogram)
    latency_histogram: Histogram = field(default_factory=Histogram)

    def add(self, other: "Usage") -> None:
        self.conversations += other.conversations
        self.messages += other.messages
        self.token_replies += other.token_replies
        self.tokens += other.tokens
        self.tokens_histogram = self.tokens_histogram.merged(other.tokens_histogram)
        self.cost_usd += other.cost_usd
        self.thumbs_up += other.thumbs_up
        self.thumbs_down += other.thumbs_down
        self.rating_sum += other.rating_sum
        self.rating_count += other.rating_count
        self.fallback_count += other.fallback_count
        self.guardrail_blocks += other.guardrail_blocks
        self.first_token_histogram = self.first_token_histogram.merged(other.first_token_histogram)
        self.latency_histogram = self.latency_histogram.merged(other.latency_histogram)

    @classmethod
    def of_row(cls, row: UsageDaily) -> "Usage":
        return cls(
            conversations=row.conversations,
            messages=row.messages,
            token_replies=row.token_replies,
            tokens=row.tokens,
            tokens_histogram=Histogram.from_stored(row.tokens_histogram),
            cost_usd=row.cost_usd,
            thumbs_up=row.thumbs_up,
            thumbs_down=row.thumbs_down,
            rating_sum=row.rating_sum,
            rating_count=row.rating_count,
            fallback_count=row.fallback_count,
            guardrail_blocks=row.guardrail_blocks,
            first_token_histogram=Histogram.from_stored(row.first_token_histogram),
            latency_histogram=Histogram.from_stored(row.latency_histogram),
        )

    def row(
        self, organisation_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, day: date
    ) -> UsageDaily:
        return UsageDaily(
            organisation_id=organisation_id,
            agent_id=agent_id,
            agent_version_id=version_id,
            day=day,
            conversations=self.conversations,
            messages=self.messages,
            token_replies=self.token_replies,
            tokens=self.tokens,
            tokens_histogram=self.tokens_histogram.stored(),
            cost_usd=self.cost_usd.quantize(DOLLARS),
            thumbs_up=self.thumbs_up,
            thumbs_down=self.thumbs_down,
            rating_sum=self.rating_sum,
            rating_count=self.rating_count,
            fallback_count=self.fallback_count,
            guardrail_blocks=self.guardrail_blocks,
            first_token_histogram=self.first_token_histogram.stored(),
            latency_histogram=self.latency_histogram.stored(),
        )


@dataclass
class VersionDay:
    """One Agent Version's usage on one day, with the Organisation and Agent it belongs to."""

    organisation_id: uuid.UUID
    agent_id: uuid.UUID
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class Only:
    """Which usage to work out: one Agent's, or every Organisation's whose rollup for the day
    isn't final yet (``unfinalised``)."""

    agent_id: uuid.UUID | None = None
    unfinalised: bool = False


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(), tzinfo=UTC)
    return start, start + timedelta(days=1)


def _visitor_replies(day: date, only: Only) -> list[ColumnElement[bool]]:
    start, end = day_bounds(day)
    conditions = [
        Message.role == MessageRole.ASSISTANT,
        Message.agent_version_id.is_not(None),
        Conversation.is_playground.is_(False),
        Message.created_at >= start,
        Message.created_at < end,
    ]
    if only.agent_id is not None:
        conditions.append(Conversation.agent_id == only.agent_id)
    if only.unfinalised:
        conditions.append(
            ~exists().where(
                UsageRollupState.organisation_id == Message.organisation_id,
                UsageRollupState.finalised_through >= day,
            )
        )
    return conditions


def _first_replies(day: date, only: Only, *, per_version: bool) -> Select[Any]:
    """Visitor Conversations (each with its Organisation and Agent, and with ``per_version``
    each Version) whose first reply (from that Version) was made on ``day``."""
    start, end = day_bounds(day)
    active = (
        select(Message.conversation_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*_visitor_replies(day, only))
    )
    keys: list[InstrumentedAttribute[Any]] = [
        Message.conversation_id,
        Conversation.organisation_id,
        Conversation.agent_id,
    ]
    if per_version:
        keys.append(Message.agent_version_id)
    first = func.min(Message.created_at)
    return (
        select(*keys)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.role == MessageRole.ASSISTANT,
            Message.agent_version_id.is_not(None),
            Message.conversation_id.in_(active),
        )
        .group_by(*keys)
        .having(and_(first >= start, first < end))
    )


async def usage_on(session: AsyncSession, day: date, only: Only) -> dict[uuid.UUID, VersionDay]:
    """Each Agent Version's usage on ``day``, by Version ID."""
    found: dict[uuid.UUID, VersionDay] = {}

    def at(organisation_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID) -> Usage:
        entry = found.setdefault(version_id, VersionDay(organisation_id, agent_id))
        return entry.usage

    replies = await session.execute(
        select(
            Message.organisation_id,
            Conversation.agent_id,
            Message.agent_version_id,
            Message.model_name,
            Message.input_tokens,
            Message.output_tokens,
            Message.cost_usd,
            Message.fallback,
            Message.first_token_ms,
            Message.latency_ms,
            Message.guardrail_outcomes,
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*_visitor_replies(day, only))
    )
    for reply in replies:
        usage = at(reply.organisation_id, reply.agent_id, reply.agent_version_id)
        usage.messages += 1
        # A fallback reply or a refusal asked no model: it has no model and no tokens to count.
        if reply.model_name is not None:
            tokens = (reply.input_tokens or 0) + (reply.output_tokens or 0)
            usage.token_replies += 1
            usage.tokens += tokens
            usage.tokens_histogram.add(tokens)
        usage.cost_usd += reply.cost_usd or 0
        usage.fallback_count += reply.fallback
        usage.guardrail_blocks += blocked(reply.guardrail_outcomes)
        usage.first_token_histogram.add(reply.first_token_ms or 0)
        usage.latency_histogram.add(reply.latency_ms or 0)

    started = (await session.execute(_first_replies(day, only, per_version=True))).all()
    for _, organisation_id, agent_id, version_id in started:
        at(organisation_id, agent_id, version_id).conversations += 1

    thumbs = await session.execute(
        select(
            Message.organisation_id,
            Conversation.agent_id,
            MessageFeedback.agent_version_id,
            MessageFeedback.rating,
            func.count(),
        )
        .join(Message, Message.id == MessageFeedback.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*_visitor_replies(day, only))
        .group_by(
            Message.organisation_id,
            Conversation.agent_id,
            MessageFeedback.agent_version_id,
            MessageFeedback.rating,
        )
    )
    for organisation_id, agent_id, version_id, rating, count in thumbs:
        # Never None: a Visitor reply is always a Version's.
        usage = at(organisation_id, agent_id, cast(uuid.UUID, version_id))
        if rating == Thumb.UP:
            usage.thumbs_up += count
        else:
            usage.thumbs_down += count

    first = _first_replies(day, only, per_version=False).subquery()
    ratings = await session.execute(
        select(
            first.c.organisation_id,
            first.c.agent_id,
            ConversationRating.agent_version_id,
            func.sum(ConversationRating.score),
            func.count(),
        )
        .join(first, first.c.conversation_id == ConversationRating.conversation_id)
        .where(
            ConversationRating.score.is_not(None),
            ConversationRating.agent_version_id.is_not(None),
        )
        .group_by(first.c.organisation_id, first.c.agent_id, ConversationRating.agent_version_id)
    )
    for organisation_id, agent_id, version_id, total, count in ratings:
        usage = at(organisation_id, agent_id, version_id)
        usage.rating_sum += total
        usage.rating_count += count
    return found
