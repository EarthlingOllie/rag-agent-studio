"""The analytics query interface: ``version_metrics``, each Agent Version's KPIs over a range
of UTC days, and ``time_series``, one metric of an Agent per day, week or month, with Live
History markers and the Project's Document changes (a confounder). Days before today come
from the ``usage_daily`` rollups; today, the live partial day, is worked out from the raw
tables. Playground Conversations never count in either. ``org_cost`` is what the Organisation
spent over a range of UTC days, by Project or by Agent, with Playground replies' cost in a
separate column, read from the raw Messages: the rollups never hold Playground usage.

Percentiles come from the merged histograms; Wilson intervals are worked out here, from the
counts. A KPI whose sample is smaller than ``LOW_CONFIDENCE_BELOW`` is flagged low confidence."""

import enum
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.agents.models import Agent, AgentVersion, LiveHistoryEntry
from app.agents.service import get_agent
from app.analytics.models import UsageDaily
from app.analytics.stats import Interval, wilson
from app.analytics.usage import DOLLARS, Only, Usage, day_bounds, usage_on
from app.audit.models import AuditEvent
from app.conversations.models import Conversation, Message, MessageRole
from app.documents.models import Document
from app.projects.models import Project
from app.tenancy.repository import OrganisationScope

# Fewer votes, ratings or Conversations than this is a small sample: low confidence.
LOW_CONFIDENCE_BELOW = 30


class VersionNotFoundError(Exception):
    """A Version asked for isn't one of the Agent's."""


@dataclass(frozen=True)
class VersionKpis:
    version: AgentVersion
    is_live: bool
    usage: Usage

    @property
    def thumbs(self) -> int:
        return self.usage.thumbs_up + self.usage.thumbs_down

    @property
    def thumbs_up_rate(self) -> float | None:
        return self.usage.thumbs_up / self.thumbs if self.thumbs else None

    @property
    def thumbs_up_interval(self) -> Interval | None:
        return wilson(self.usage.thumbs_up, self.thumbs)

    @property
    def mean_tokens(self) -> float | None:
        usage = self.usage
        return usage.tokens / usage.token_replies if usage.token_replies else None

    @property
    def mean_rating(self) -> float | None:
        usage = self.usage
        return usage.rating_sum / usage.rating_count if usage.rating_count else None

    @property
    def fallback_rate(self) -> float | None:
        usage = self.usage
        return usage.fallback_count / usage.messages if usage.messages else None

    @property
    def block_rate(self) -> float | None:
        """The share of replies that were the refusal text: the input Guardrail blocked the
        question."""
        usage = self.usage
        return usage.guardrail_blocks / usage.messages if usage.messages else None

    @property
    def cost_total(self) -> Decimal:
        return self.usage.cost_usd.quantize(DOLLARS)

    @property
    def cost_per_conversation(self) -> Decimal | None:
        usage = self.usage
        if not usage.conversations:
            return None
        return (usage.cost_usd / usage.conversations).quantize(DOLLARS)


def low_confidence(sample: int) -> bool:
    return sample < LOW_CONFIDENCE_BELOW


async def version_metrics(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_ids: Sequence[uuid.UUID],
    start: date,
    end: date,
    today: date,
) -> list[VersionKpis]:
    """The KPIs of the Agent's chosen Versions (every Version when none is chosen), oldest
    Version first, over the UTC days ``start`` to ``end`` inclusive; ``today`` is the current
    UTC day. Raises ``AgentNotFoundError``, or ``VersionNotFoundError`` for a Version that isn't
    the Agent's."""
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    query = select(AgentVersion).where(AgentVersion.agent_id == agent.id)
    if version_ids:
        query = query.where(AgentVersion.id.in_(version_ids))
    versions = list(await session.scalars(query.order_by(AgentVersion.number)))
    if version_ids and len(versions) != len(set(version_ids)):
        raise VersionNotFoundError
    usage = {version.id: Usage() for version in versions}
    rolled = await session.scalars(
        select(UsageDaily).where(
            UsageDaily.agent_version_id.in_(usage),
            UsageDaily.day >= start,
            UsageDaily.day <= min(end, today - timedelta(days=1)),
        )
    )
    for row in rolled:
        usage[row.agent_version_id].add(Usage.of_row(row))
    if start <= today <= end:
        for version_id, entry in (await usage_on(session, today, Only(agent_id=agent.id))).items():
            # Only the chosen Versions: the live day covers the whole Agent.
            if version_id in usage:
                usage[version_id].add(entry.usage)
    return [
        VersionKpis(version, version.id == agent.live_version_id, usage[version.id])
        for version in versions
    ]


class CostGroup(enum.StrEnum):
    """What org cost is broken down by."""

    PROJECT = "project"
    AGENT = "agent"


@dataclass(frozen=True)
class CostLine:
    """What one Project (or one Agent, with its Project) cost over the period: its Visitor
    replies and, separately, its Playground replies, at the prices frozen when each was made."""

    project_id: uuid.UUID
    project_name: str
    agent_id: uuid.UUID | None
    agent_name: str | None
    visitor_usd: Decimal
    playground_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        return self.visitor_usd + self.playground_usd


async def _visitor_cost(
    session: AsyncSession, organisation_id: uuid.UUID, start: date, end: date, today: date
) -> dict[uuid.UUID, Decimal]:
    """Each Agent's Visitor replies' cost over the days: rollups before today, then today."""
    cost: defaultdict[uuid.UUID, Decimal] = defaultdict(Decimal)
    rolled = await session.execute(
        select(UsageDaily.agent_id, func.sum(UsageDaily.cost_usd))
        .where(
            UsageDaily.organisation_id == organisation_id,
            UsageDaily.day >= start,
            UsageDaily.day <= min(end, today - timedelta(days=1)),
        )
        .group_by(UsageDaily.agent_id)
    )
    for agent_id, total in rolled:
        cost[agent_id] += total
    if start <= today <= end:
        live = await usage_on(session, today, Only(organisation_id=organisation_id))
        for entry in live.values():
            cost[entry.agent_id] += entry.usage.cost_usd
    return cost


async def _playground_cost(
    session: AsyncSession, organisation_id: uuid.UUID, start: date, end: date
) -> dict[uuid.UUID, Decimal]:
    """Each Agent's Playground replies' cost over the days, from the raw Messages."""
    first, _ = day_bounds(start)
    _, after = day_bounds(end)
    rows = await session.execute(
        select(Conversation.agent_id, func.sum(Message.cost_usd))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.organisation_id == organisation_id,
            Message.role == MessageRole.ASSISTANT,
            Conversation.is_playground.is_(True),
            Message.created_at >= first,
            Message.created_at < after,
        )
        .group_by(Conversation.agent_id)
    )
    # A reply with no known price adds nothing.
    return {agent_id: total or Decimal(0) for agent_id, total in rows}


async def org_cost(
    session: AsyncSession,
    scope: OrganisationScope,
    group_by: CostGroup,
    start: date,
    end: date,
    today: date,
) -> list[CostLine]:
    """What the Organisation spent over the UTC days ``start`` to ``end`` inclusive (``today``
    is the current UTC day), one line per Project or per Agent that replied in the period,
    most expensive first. Archived Projects and Agents are included: they spent it."""
    visitor = await _visitor_cost(session, scope.organisation_id, start, end, today)
    playground = await _playground_cost(session, scope.organisation_id, start, end)
    agents = await session.execute(
        select(Agent.id, Agent.name, Project.id, Project.name)
        .join(Project, Project.id == Agent.project_id)
        .where(
            Agent.organisation_id == scope.organisation_id,
            Agent.id.in_(visitor.keys() | playground.keys()),
        )
    )
    by_agent = group_by is CostGroup.AGENT
    names: dict[uuid.UUID, tuple[uuid.UUID, str, uuid.UUID | None, str | None]] = {}
    visitor_usd: defaultdict[uuid.UUID, Decimal] = defaultdict(Decimal)
    playground_usd: defaultdict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for agent_id, agent_name, project_id, project_name in agents:
        key = agent_id if by_agent else project_id
        names[key] = (
            project_id,
            project_name,
            *((agent_id, agent_name) if by_agent else (None, None)),
        )
        visitor_usd[key] += visitor.get(agent_id, Decimal(0))
        playground_usd[key] += playground.get(agent_id, Decimal(0))
    lines = [
        CostLine(
            *names[key], visitor_usd[key].quantize(DOLLARS), playground_usd[key].quantize(DOLLARS)
        )
        for key in names
    ]
    return sorted(
        lines, key=lambda line: (-line.total_usd, line.project_name, line.agent_name or "")
    )


class TimeSeriesMetric(enum.StrEnum):
    """What a time series measures, over each of its periods."""

    CONVERSATIONS = "conversations"
    REPLIES = "replies"
    COST_USD = "cost_usd"
    MEAN_TOKENS = "mean_tokens"
    THUMBS_UP_RATE = "thumbs_up_rate"
    MEAN_RATING = "mean_rating"
    FALLBACK_RATE = "fallback_rate"
    P95_LATENCY_MS = "p95_latency_ms"


class TimeSeriesGranularity(enum.StrEnum):
    DAY = "day"
    # ISO weeks, Monday to Sunday.
    WEEK = "week"
    MONTH = "month"


def _rate(part: int, n: int) -> tuple[float | None, int]:
    return (part / n if n else None), n


# Each metric's value over some usage (None without a sample), and its sample size.
_MEASURES: dict[TimeSeriesMetric, Callable[[Usage], tuple[float | None, int]]] = {
    TimeSeriesMetric.CONVERSATIONS: lambda u: (u.conversations, u.conversations),
    TimeSeriesMetric.REPLIES: lambda u: (u.messages, u.messages),
    TimeSeriesMetric.COST_USD: lambda u: (float(u.cost_usd.quantize(DOLLARS)), u.conversations),
    TimeSeriesMetric.MEAN_TOKENS: lambda u: _rate(u.tokens, u.token_replies),
    TimeSeriesMetric.THUMBS_UP_RATE: lambda u: _rate(u.thumbs_up, u.thumbs_up + u.thumbs_down),
    TimeSeriesMetric.MEAN_RATING: lambda u: _rate(u.rating_sum, u.rating_count),
    TimeSeriesMetric.FALLBACK_RATE: lambda u: _rate(u.fallback_count, u.messages),
    TimeSeriesMetric.P95_LATENCY_MS: lambda u: (
        u.latency_histogram.percentile(0.95),
        u.latency_histogram.count,
    ),
}

# The first day of the period (day, ISO week or month) a day is in.
_PERIOD_START: dict[TimeSeriesGranularity, Callable[[date], date]] = {
    TimeSeriesGranularity.DAY: lambda day: day,
    TimeSeriesGranularity.WEEK: lambda day: day - timedelta(days=day.weekday()),
    TimeSeriesGranularity.MONTH: lambda day: day.replace(day=1),
}


def _periods(start: date, end: date, granularity: TimeSeriesGranularity) -> list[tuple[date, date]]:
    """The periods covering ``start`` to ``end``, each clipped to the range."""
    period_start = _PERIOD_START[granularity]
    found: list[tuple[date, date]] = []
    day = start
    while day <= end:
        following = day + timedelta(days=1)
        while following <= end and period_start(following) == period_start(day):
            following += timedelta(days=1)
        found.append((day, following - timedelta(days=1)))
        day = following
    return found


@dataclass(frozen=True)
class Point:
    start: date
    end: date
    value: float | None
    n: int


@dataclass(frozen=True)
class Marker:
    """A change of the Live Version: one Live History entry."""

    occurred_at: datetime
    action: str
    from_version: AgentVersion | None
    to_version: AgentVersion


@dataclass(frozen=True)
class DocumentChanges:
    """What changed in the Project's Knowledge Base during a range: Documents added, replaced or
    processed again (still there), and Documents deleted."""

    changed: int
    deleted: int


@dataclass(frozen=True)
class TimeSeries:
    points: list[Point]
    markers: list[Marker]
    document_changes: DocumentChanges


async def _markers(
    session: AsyncSession, agent_id: uuid.UUID, since: datetime, until: datetime
) -> list[Marker]:
    before = aliased(AgentVersion)
    after = aliased(AgentVersion)
    rows = await session.execute(
        select(LiveHistoryEntry, before, after)
        .outerjoin(before, before.id == LiveHistoryEntry.from_version_id)
        .join(after, after.id == LiveHistoryEntry.to_version_id)
        .where(
            LiveHistoryEntry.agent_id == agent_id,
            LiveHistoryEntry.occurred_at >= since,
            LiveHistoryEntry.occurred_at < until,
        )
        .order_by(LiveHistoryEntry.seq)
    )
    return [Marker(entry.occurred_at, entry.action, old, new) for entry, old, new in rows]


async def _document_changes(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    project_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> DocumentChanges:
    def within(column: InstrumentedAttribute[datetime]) -> ColumnElement[bool]:
        return and_(column >= since, column < until)

    changed = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.project_id == project_id,
            or_(within(Document.created_at), within(Document.updated_at)),
        )
    )
    deleted = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.organisation_id == organisation_id,
            AuditEvent.action == "document.deleted",
            AuditEvent.before["project_id"].astext == str(project_id),
            within(AuditEvent.occurred_at),
        )
    )
    return DocumentChanges(changed=changed or 0, deleted=deleted or 0)


async def time_series(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    metric: TimeSeriesMetric,
    granularity: TimeSeriesGranularity,
    start: date,
    end: date,
    today: date,
) -> TimeSeries:
    """The metric over every Version of the Agent, per period of the UTC days ``start`` to
    ``end`` inclusive (each period clipped to the range), including today so far; with the
    Live History entries made during the range and the Project's Document changes during it.
    Raises ``AgentNotFoundError``."""
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    daily: dict[date, Usage] = {}
    rolled = await session.scalars(
        select(UsageDaily).where(
            UsageDaily.agent_id == agent.id,
            UsageDaily.day >= start,
            UsageDaily.day <= min(end, today - timedelta(days=1)),
        )
    )
    for row in rolled:
        daily.setdefault(row.day, Usage()).add(Usage.of_row(row))
    if start <= today <= end:
        for version_day in (await usage_on(session, today, Only(agent_id=agent.id))).values():
            daily.setdefault(today, Usage()).add(version_day.usage)
    points = []
    for first, last in _periods(start, end, granularity):
        usage = Usage()
        for day, used in daily.items():
            if first <= day <= last:
                usage.add(used)
        value, n = _MEASURES[metric](usage)
        points.append(Point(first, last, value, n))
    since, _ = day_bounds(start)
    _, until = day_bounds(end)
    return TimeSeries(
        points=points,
        markers=await _markers(session, agent.id, since, until),
        document_changes=await _document_changes(
            session, scope.organisation_id, agent.project_id, since, until
        ),
    )
