"""The hourly alerts, run after each rollup: the Block rate alert and the Live score drop alert.
Each sets a flag on the Agent (the Studio's badge) and emails every Owner of its Organisation once
when raised; the first run that no longer finds the problem clears it.

Block rate alert: every Agent's Guardrail block rate over the last hour is compared with its
baseline, the week before that hour. A spike is at least ``SPIKE_MIN_BLOCKS`` blocked Visitor
messages in the hour, making up at least ``SPIKE_MIN_RATE`` of the hour's Visitor messages and at
least ``SPIKE_FACTOR`` times the baseline's block rate. Only Visitor Conversations count: the
Playground never does. Each Agent records the end of the last hour it was checked for; a run
also checks each hour since then (one with Visitor replies of the Agent), oldest first, so a
spike while Beat was down is still alerted on.

Live score drop alert: once an Agent's Live Version has ``DROP_MIN_JUDGED`` judged Live Verdicts
on replies since it became Live, its Live score is compared with the previous Live Version's (the
one it replaced, in Live History) over that Version's last ``DROP_WINDOW`` as Live, which needs
``DROP_MIN_JUDGED`` too. A drop is at least ``DROP_MIN_POINTS`` lower and lower by a one-sided
pooled two-proportion z-test at 95%. Any change of the Live Version also clears it
(``app.agents.versions``)."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Integer,
    Select,
    and_,
    case,
    func,
    or_,
    select,
    type_coerce,
    update,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentVersion, LiveHistoryEntry
from app.analytics.stats import clearly_lower
from app.conversations.models import Conversation, Message, MessageRole
from app.evaluation.models import LiveStatus, LiveVerdict
from app.mail import templates
from app.mail.port import Mailer
from app.tenancy.models import Member, Membership, Role

WINDOW = timedelta(hours=1)
BASELINE = timedelta(days=7)
SPIKE_MIN_BLOCKS = 5
SPIKE_MIN_RATE = 0.2
SPIKE_FACTOR = 3
DROP_MIN_JUDGED = 30
DROP_WINDOW = timedelta(days=30)
DROP_MIN_POINTS = 0.05


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


def _visitor_replies() -> list[ColumnElement[bool]]:
    return [
        Message.role == MessageRole.ASSISTANT,
        Message.agent_version_id.is_not(None),
        Conversation.is_playground.is_(False),
    ]


async def _rates(
    session: AsyncSession, at: datetime, agents: Collection[uuid.UUID] | None
) -> dict[uuid.UUID, Rates]:
    """Each Agent with Visitor replies in the hour up to ``at`` (of ``agents``, or all): its
    rates."""
    start = at - WINDOW
    only = [] if agents is None else [Conversation.agent_id.in_(agents)]
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
            *_visitor_replies(),
            *only,
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


async def _owners(session: AsyncSession, agent: Agent) -> list[tuple[str, str]]:
    """The name and email of every Owner of the Agent's Organisation."""
    rows = await session.execute(
        select(Member.name, Member.email)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == agent.organisation_id, Membership.role == Role.OWNER)
        .order_by(Member.email)
    )
    return [(name, email) for name, email in rows]


async def _email_owners(
    session: AsyncSession, agent: Agent, rates: Rates, *, mailer: Mailer, studio_url: str
) -> None:
    owners = await _owners(session, agent)
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


async def _missed_hours(session: AsyncSession, at: datetime) -> dict[datetime, set[uuid.UUID]]:
    """The hours a stopped Beat missed: for each Agent checked before, every hour since the
    end of its last checked hour, in steps of an hour, that holds Visitor replies of the Agent
    and ended before ``at`` (the last may overlap the hour up to ``at``, which is checked
    anyway). Each hour's end, with its Agents."""
    since = Agent.block_rate_checked_at
    hours = func.ceil(func.extract("epoch", Message.created_at - since) / WINDOW.total_seconds())
    # Never None: only Agents checked before have hours since.
    end = type_coerce(
        since + func.make_interval(0, 0, 0, 0, hours.cast(Integer)), DateTime(timezone=True)
    )
    rows = await session.execute(
        select(Conversation.agent_id, end)
        .distinct()
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Agent, Agent.id == Conversation.agent_id)
        .where(*_visitor_replies(), Message.created_at > since, end < at)
    )
    missed: dict[datetime, set[uuid.UUID]] = {}
    for agent_id, hour_end in rows:
        missed.setdefault(hour_end, set()).add(agent_id)
    return missed


async def check_block_rates(
    session: AsyncSession, at: datetime, *, mailer: Mailer, studio_url: str
) -> None:
    """Checks every hour each Agent missed since it was last checked (``_missed_hours``), oldest
    first, then the hour before ``at`` for every Agent, and records ``at`` as the end of the
    last hour covered (a run by hand for an earlier time leaves a later one)."""
    missed = await _missed_hours(session, at)
    for hour_end in sorted(missed):
        await _check_hour(session, hour_end, missed[hour_end], mailer=mailer, studio_url=studio_url)
    await _check_hour(session, at, None, mailer=mailer, studio_url=studio_url)
    await session.execute(
        update(Agent)
        .where(or_(Agent.block_rate_checked_at.is_(None), Agent.block_rate_checked_at < at))
        .values(block_rate_checked_at=at)
    )
    await session.commit()


async def _check_hour(
    session: AsyncSession,
    at: datetime,
    agents: Collection[uuid.UUID] | None,
    *,
    mailer: Mailer,
    studio_url: str,
) -> None:
    """Raises the Block rate alert of every Agent (of ``agents``, or all) whose block rate
    spiked in the hour before ``at`` (emailing its Owners), and clears it on every other one.
    An Agent already alerted is not emailed again while the spike lasts."""
    rates = await _rates(session, at, agents)
    spiking = {agent_id for agent_id, found in rates.items() if found.spike}
    only = [] if agents is None else [Agent.id.in_(agents)]
    await session.execute(
        update(Agent)
        .where(Agent.block_rate_alert_at.is_not(None), Agent.id.not_in(spiking), *only)
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


@dataclass(frozen=True)
class Scores:
    """An Agent's Live Version and the previous Live Version, with their judged and passed Live
    Verdicts in the windows compared."""

    version_id: uuid.UUID
    judged: int
    passed: int
    previous_id: uuid.UUID
    previous_judged: int
    previous_passed: int

    @property
    def drop(self) -> bool:
        return self.previous_judged >= DROP_MIN_JUDGED and clearly_lower(
            self.previous_passed,
            self.previous_judged,
            self.passed,
            self.judged,
            min_drop=DROP_MIN_POINTS,
        )


async def _scores(session: AsyncSession, at: datetime) -> dict[uuid.UUID, Scores]:
    """Each Agent whose Live Version replaced an earlier one and has at least
    ``DROP_MIN_JUDGED`` judged Live Verdicts on replies since: both Versions' counts."""
    # The Live History entry that made each Agent's Live Version Live.
    became = (
        select(
            LiveHistoryEntry.agent_id,
            LiveHistoryEntry.to_version_id,
            LiveHistoryEntry.from_version_id,
            LiveHistoryEntry.occurred_at,
        )
        .join(Agent, Agent.id == LiveHistoryEntry.agent_id)
        .where(
            LiveHistoryEntry.to_version_id == Agent.live_version_id,
            LiveHistoryEntry.from_version_id.is_not(None),
        )
        .ext(distinct_on(LiveHistoryEntry.agent_id))
        .order_by(LiveHistoryEntry.agent_id, LiveHistoryEntry.seq.desc())
        .subquery()
    )

    def counts(
        version: ColumnElement[uuid.UUID], *window: ColumnElement[bool]
    ) -> Select[uuid.UUID, uuid.UUID, uuid.UUID, int, int]:
        """Each Agent's judged and passed Live Verdicts of ``version`` on replies in ``window``,
        with its Live Version and the previous one."""
        return (
            select(
                became.c.agent_id,
                became.c.to_version_id,
                became.c.from_version_id,
                func.count(),
                _count(LiveVerdict.passed.is_(True)),
            )
            .join(LiveVerdict, LiveVerdict.agent_version_id == version)
            .join(Message, Message.id == LiveVerdict.message_id)
            .where(LiveVerdict.status == LiveStatus.JUDGED, *window)
            .group_by(became.c.agent_id, became.c.to_version_id, became.c.from_version_id)
        )

    current = await session.execute(
        counts(
            became.c.to_version_id,
            Message.created_at >= became.c.occurred_at,
            Message.created_at <= at,
        ).having(func.count() >= DROP_MIN_JUDGED)
    )
    found = {
        agent_id: Scores(to_id, judged, passed, from_id, 0, 0)
        for agent_id, to_id, from_id, judged, passed in current
    }
    previous = await session.execute(
        counts(
            became.c.from_version_id,
            Message.created_at >= became.c.occurred_at - DROP_WINDOW,
            Message.created_at < became.c.occurred_at,
        ).where(became.c.agent_id.in_(found))
    )
    for agent_id, _, _, judged, passed in previous:
        found[agent_id] = replace(found[agent_id], previous_judged=judged, previous_passed=passed)
    return found


def _score(passed: int, judged: int) -> str:
    return _percent(passed / judged)


async def _email_drop(
    session: AsyncSession, agent: Agent, scores: Scores, *, mailer: Mailer, studio_url: str
) -> None:
    version = await session.get_one(AgentVersion, scores.version_id)
    previous = await session.get_one(AgentVersion, scores.previous_id)
    ids = (str(agent.organisation_id), str(agent.project_id), str(agent.id))
    comparison_link = templates.version_comparison_link(
        studio_url, *ids, str(previous.id), str(version.id)
    )
    failed_link = templates.failed_live_verdicts_link(studio_url, *ids)
    for name, email in await _owners(session, agent):
        await mailer.send(
            templates.live_score_drop(
                to=email,
                name=name,
                agent_name=agent.name,
                version=version.number,
                score=_score(scores.passed, scores.judged),
                passed=scores.passed,
                judged=scores.judged,
                previous_version=previous.number,
                previous_score=_score(scores.previous_passed, scores.previous_judged),
                previous_passed=scores.previous_passed,
                previous_judged=scores.previous_judged,
                comparison_link=comparison_link,
                failed_link=failed_link,
            )
        )


async def check_live_scores(
    session: AsyncSession, at: datetime, *, mailer: Mailer, studio_url: str
) -> None:
    """Raises the Live score drop alert of every Agent whose Live Version's Live score, as of
    ``at``, is clearly lower than the previous Live Version's (emailing its Owners), and clears
    it on every other Agent. An Agent already alerted is not emailed again while the drop
    lasts."""
    scores = await _scores(session, at)
    dropping = {agent_id: found for agent_id, found in scores.items() if found.drop}
    await session.execute(
        update(Agent)
        .where(Agent.live_score_drop_alert_at.is_not(None), Agent.id.not_in(dropping))
        .values(live_score_drop_alert_at=None, live_score_drop_version_id=None)
    )
    raised: list[uuid.UUID] = []
    for agent_id in sorted(dropping):
        raised += await session.scalars(
            update(Agent)
            .where(
                Agent.id == agent_id,
                Agent.live_score_drop_alert_at.is_(None),
                # Not if another Version was made Live since: the drop was about this one.
                Agent.live_version_id == dropping[agent_id].version_id,
            )
            .values(
                live_score_drop_alert_at=at,
                live_score_drop_version_id=dropping[agent_id].version_id,
            )
            .returning(Agent.id)
        )
    await session.commit()
    for agent_id in raised:
        agent = await session.get_one(Agent, agent_id)
        await _email_drop(session, agent, dropping[agent_id], mailer=mailer, studio_url=studio_url)
