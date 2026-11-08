"""The Block rate alert: after each hourly rollup, every Agent's Guardrail block rate over the
last hour is compared with its baseline, the week before that hour. A spike raises the Agent's
alert flag (the Studio's badge) and emails every Owner of its Organisation once; the first run
that no longer finds a spike clears it.

A spike is at least ``SPIKE_MIN_BLOCKS`` blocked Visitor messages in the hour, making up at
least ``SPIKE_MIN_RATE`` of the hour's Visitor messages and at least ``SPIKE_FACTOR`` times the
baseline's block rate. Only Visitor Conversations count: the Playground never does."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.conversations.models import Conversation, Message, MessageRole
from app.mail import templates
from app.mail.port import Mailer
from app.tenancy.models import Member, Membership, Role

WINDOW = timedelta(hours=1)
BASELINE = timedelta(days=7)
SPIKE_MIN_BLOCKS = 5
SPIKE_MIN_RATE = 0.2
SPIKE_FACTOR = 3


@dataclass(frozen=True)
class Rates:
    """An Agent's Visitor replies and blocked ones, in the last hour and in the baseline."""

    blocks: int
    replies: int
    baseline_blocks: int
    baseline_replies: int

    @property
    def rate(self) -> float:
        # Only Agents with replies in the hour are checked.
        return self.blocks / self.replies

    @property
    def baseline_rate(self) -> float:
        return self.baseline_blocks / self.baseline_replies if self.baseline_replies else 0.0

    @property
    def spike(self) -> bool:
        return (
            self.blocks >= SPIKE_MIN_BLOCKS
            and self.rate >= SPIKE_MIN_RATE
            and self.rate >= SPIKE_FACTOR * self.baseline_rate
        )


def _count(condition: ColumnElement[bool]) -> ColumnElement[int]:
    return func.count(case((condition, 1)))


async def _rates(session: AsyncSession, at: datetime) -> dict[uuid.UUID, Rates]:
    """Each Agent with Visitor replies in the hour up to ``at``: its rates."""
    start = at - WINDOW
    in_window = Message.created_at > start
    is_block = Message.guardrail_outcomes.contains([{"layer": "input", "action": "blocked"}])
    rows = await session.execute(
        select(
            Conversation.agent_id,
            _count(and_(in_window, is_block)),
            _count(in_window),
            _count(and_(~in_window, is_block)),
            _count(~in_window),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.role == MessageRole.ASSISTANT,
            Message.agent_version_id.is_not(None),
            Conversation.is_playground.is_(False),
            Message.created_at > start - BASELINE,
            Message.created_at <= at,
        )
        .group_by(Conversation.agent_id)
    )
    return {
        agent_id: Rates(blocks, replies, baseline_blocks, baseline_replies)
        for agent_id, blocks, replies, baseline_blocks, baseline_replies in rows
        if replies
    }


def _percent(rate: float) -> str:
    return f"{round(rate * 100)}%"


async def _email_owners(
    session: AsyncSession, agent: Agent, rates: Rates, *, mailer: Mailer, studio_url: str
) -> None:
    owners = await session.execute(
        select(Member.name, Member.email)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == agent.organisation_id, Membership.role == Role.OWNER)
        .order_by(Member.email)
    )
    link = templates.blocked_conversations_link(
        studio_url, str(agent.organisation_id), str(agent.project_id), str(agent.id)
    )
    for name, email in owners:
        await mailer.send(
            templates.block_rate_spike(
                to=email,
                name=name,
                agent_name=agent.name,
                blocks=rates.blocks,
                replies=rates.replies,
                rate=_percent(rates.rate),
                baseline_rate=_percent(rates.baseline_rate),
                link=link,
            )
        )


async def check_block_rates(
    session: AsyncSession, at: datetime, *, mailer: Mailer, studio_url: str
) -> None:
    """Raises the Block rate alert of every Agent whose block rate spiked in the hour before
    ``at`` (emailing its Owners), and clears it on every other Agent. An Agent already
    alerted is not emailed again while the spike lasts."""
    rates = await _rates(session, at)
    spiking = {agent_id for agent_id, found in rates.items() if found.spike}
    await session.execute(
        update(Agent)
        .where(Agent.block_rate_alert_at.is_not(None), Agent.id.not_in(spiking))
        .values(block_rate_alert_at=None)
    )
    raised = list(
        await session.scalars(
            update(Agent)
            .where(Agent.id.in_(spiking), Agent.block_rate_alert_at.is_(None))
            .values(block_rate_alert_at=at)
            .returning(Agent.id)
        )
    )
    await session.commit()
    for agent_id in sorted(raised):
        agent = await session.get_one(Agent, agent_id)
        await _email_owners(session, agent, rates[agent_id], mailer=mailer, studio_url=studio_url)
