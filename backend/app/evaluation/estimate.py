"""A Run's estimated Cost, shown in the Evaluate dialog before it starts and stored on the Run.

It is the cases, times the sides, times the repeats, times each side's mean Cost per reply over
the last 30 days, plus judging every answer. A Version's mean comes from its Usage rollups
(Visitor replies, the days before today), the Draft's from the Agent's Playground replies to the
Draft. A side with no replies in that time is priced from its chat model with ``ALLOWANCE``, the
fixed per-judgement token allowance, which also prices each judgement at the judge's model.
Prices are those in force now. Unknown when a price it needs is unknown.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import UsageDaily
from app.conversations.models import DRAFT, Conversation, Message, MessageRole
from app.credentials.models import ProviderCredential
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import PriceEntry, TokenUsage, cost

HISTORY = timedelta(days=30)
# The tokens one judgement (and a reply with no history) is assumed to use: the question, the
# answer, its cited excerpts and the Reference answer in, the Verdicts out.
ALLOWANCE = TokenUsage(input_tokens=2_000, output_tokens=200)
# To the billionth of a dollar, as a Run stores it.
NANO = Decimal("0.000000001")


@dataclass(frozen=True)
class EstimateSide:
    """A side as the estimate prices it: the Agent Version (None for the Draft) and the chat
    model it answers with."""

    agent_id: uuid.UUID
    agent_version_id: uuid.UUID | None
    credential: ProviderCredential
    model: str


@dataclass(frozen=True)
class Estimate:
    cases: int
    sides: int
    repeats: int
    # In US dollars; None when a price it needed is unknown.
    answers_usd: Decimal | None
    judging_usd: Decimal | None

    @property
    def total_usd(self) -> Decimal | None:
        if self.answers_usd is None or self.judging_usd is None:
            return None
        return self.answers_usd + self.judging_usd


async def _version_mean(
    session: AsyncSession, version_id: uuid.UUID, now: datetime
) -> Decimal | None:
    today = now.astimezone(UTC).date()
    spent, replies = (
        await session.execute(
            select(func.sum(UsageDaily.cost_usd), func.sum(UsageDaily.messages)).where(
                UsageDaily.agent_version_id == version_id,
                UsageDaily.day >= today - HISTORY,
                UsageDaily.day < today,
            )
        )
    ).one()
    return None if not replies else (spent or Decimal(0)) / replies


async def _draft_mean(session: AsyncSession, agent_id: uuid.UUID, now: datetime) -> Decimal | None:
    spent, replies = (
        await session.execute(
            select(func.sum(Message.cost_usd), func.count(Message.cost_usd))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.agent_id == agent_id,
                Conversation.is_playground.is_(True),
                Message.role == MessageRole.ASSISTANT,
                Message.config_source == DRAFT,
                Message.created_at >= now - HISTORY,
                Message.created_at <= now,
            )
        )
    ).one()
    return None if not replies else (spent or Decimal(0)) / replies


async def _allowance(
    session: AsyncSession,
    credential: ProviderCredential,
    model: str,
    now: datetime,
    table: tuple[PriceEntry, ...],
) -> Decimal | None:
    return cost(await credential_pricing(session, credential), model, ALLOWANCE, now, table)


async def estimate(
    session: AsyncSession,
    sides: list[EstimateSide],
    judge_credential: ProviderCredential,
    judge_model: str,
    *,
    cases: int,
    repeats: int,
    now: datetime,
) -> Estimate:
    """What a Run of ``cases`` cases on ``sides``, each answered ``repeats`` times and every
    answer judged, is expected to cost at ``now``."""
    table = await price_table(session)
    per_reply: list[Decimal | None] = []
    for side in sides:
        mean = (
            await _draft_mean(session, side.agent_id, now)
            if side.agent_version_id is None
            else await _version_mean(session, side.agent_version_id, now)
        )
        if mean is None:
            mean = await _allowance(session, side.credential, side.model, now, table)
        per_reply.append(mean)
    answers = cases * repeats
    judgement = await _allowance(session, judge_credential, judge_model, now, table)
    return Estimate(
        cases=cases,
        sides=len(sides),
        repeats=repeats,
        answers_usd=None
        if None in per_reply
        else (answers * sum((m for m in per_reply if m is not None), Decimal(0))).quantize(NANO),
        judging_usd=None
        if judgement is None
        else (answers * len(sides) * judgement).quantize(NANO),
    )
