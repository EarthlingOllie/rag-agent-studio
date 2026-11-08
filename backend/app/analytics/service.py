"""The analytics query interface: ``version_metrics``, each Agent Version's KPIs over a range of
UTC days. Days before today come from the ``usage_daily`` rollups; today, the live partial day,
is worked out from the raw tables. Playground Conversations never count.

Percentiles come from the merged histograms; Wilson intervals are worked out here, from the
counts. A KPI whose sample is smaller than ``LOW_CONFIDENCE_BELOW`` is flagged low confidence."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentVersion
from app.agents.service import get_agent
from app.analytics.models import UsageDaily
from app.analytics.stats import Interval, wilson
from app.analytics.usage import DOLLARS, Only, Usage, usage_on
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
