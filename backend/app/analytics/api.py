"""Studio routes for Version KPIs (an Agent's Versions' key numbers over a range of UTC days)
and the time series (one metric of the Agent per day, week or month, with Live History markers
and a confounder note's Document changes). Editors and Owners may read them. Playground
Conversations never count. Org cost (what the Organisation spent over a range of UTC days,
by Project or by Agent, with Playground usage in a separate column) is for Owners only."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.models import AgentVersion
from app.agents.service import AgentNotFoundError
from app.analytics import service
from app.auth.api import Db
from app.playground.api import Dollars
from app.projects.service import ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import OwnerScope, Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}", tags=["analytics"]
)

cost_router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["analytics"])

DEFAULT_DAYS = 30
MAX_DAYS = 366


class TokensOut(BaseModel):
    # Replies that asked a model (fallback replies and refusals ask none).
    n: int
    # Input plus output tokens per reply; null without a reply that asked a model.
    mean: float | None
    p95: float | None


class CostOut(BaseModel):
    # The replies' costs, frozen when each was made, in US dollars.
    total_usd: Dollars
    # Null without a Conversation.
    per_conversation_usd: Dollars | None


class ThumbsUpOut(BaseModel):
    up: int
    down: int
    # The sample size: replies given a thumbs up or down.
    n: int
    # The share of thumbs up, and its Wilson 95% interval; null without a vote.
    rate: float | None
    low: float | None
    high: float | None
    # Fewer than 30 votes.
    low_confidence: bool


class RatingOut(BaseModel):
    # Conversations rated; the mean of their current Conversation Ratings (1 to 5).
    n: int
    mean: float | None
    # Fewer than 30 ratings.
    low_confidence: bool


class FallbackOut(BaseModel):
    count: int
    # The share of replies that were the fallback text; null without a reply.
    rate: float | None


class GuardrailBlocksOut(BaseModel):
    # Replies that were the refusal text because the input Guardrail blocked the question.
    count: int
    # The block rate: their share of the replies; null without a reply.
    rate: float | None


class LatencyOut(BaseModel):
    n: int
    # p95 milliseconds to the first token, and to the whole reply.
    first_token_p95_ms: float | None
    total_p95_ms: float | None


class VersionKpisOut(BaseModel):
    version_id: uuid.UUID
    number: int
    is_live: bool
    # Visitor Conversations the Version replied in, and its replies.
    conversations: int
    messages: int
    # Fewer than 30 Conversations.
    low_confidence: bool
    tokens: TokensOut
    cost: CostOut
    thumbs_up: ThumbsUpOut
    rating: RatingOut
    fallback: FallbackOut
    guardrail_blocks: GuardrailBlocksOut
    latency: LatencyOut


class VersionMetricsOut(BaseModel):
    agent_id: uuid.UUID
    # The UTC days covered, both inclusive.
    start: date
    end: date
    versions: list[VersionKpisOut]


def _out(kpis: service.VersionKpis) -> VersionKpisOut:
    usage = kpis.usage
    interval = kpis.thumbs_up_interval
    return VersionKpisOut(
        version_id=kpis.version.id,
        number=kpis.version.number,
        is_live=kpis.is_live,
        conversations=usage.conversations,
        messages=usage.messages,
        low_confidence=service.low_confidence(usage.conversations),
        tokens=TokensOut(
            n=usage.token_replies,
            mean=kpis.mean_tokens,
            p95=usage.tokens_histogram.percentile(0.95),
        ),
        cost=CostOut(total_usd=kpis.cost_total, per_conversation_usd=kpis.cost_per_conversation),
        thumbs_up=ThumbsUpOut(
            up=usage.thumbs_up,
            down=usage.thumbs_down,
            n=kpis.thumbs,
            rate=kpis.thumbs_up_rate,
            low=None if interval is None else interval.low,
            high=None if interval is None else interval.high,
            low_confidence=service.low_confidence(kpis.thumbs),
        ),
        rating=RatingOut(
            n=usage.rating_count,
            mean=kpis.mean_rating,
            low_confidence=service.low_confidence(usage.rating_count),
        ),
        fallback=FallbackOut(count=usage.fallback_count, rate=kpis.fallback_rate),
        guardrail_blocks=GuardrailBlocksOut(count=usage.guardrail_blocks, rate=kpis.block_rate),
        latency=LatencyOut(
            n=usage.latency_histogram.count,
            first_token_p95_ms=usage.first_token_histogram.percentile(0.95),
            total_p95_ms=usage.latency_histogram.percentile(0.95),
        ),
    )


def _bad_range(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _range(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """The UTC days asked for, defaulting to the last 30 days to today; refuses a range that
    runs backwards or is longer than ``MAX_DAYS``."""
    last = end or today
    first = start or last - timedelta(days=DEFAULT_DAYS - 1)
    if first > last:
        raise _bad_range("The start must not be after the end.")
    if (last - first).days >= MAX_DAYS:
        raise _bad_range(f"The range can be at most {MAX_DAYS} days.")
    return first, last


_START = Query(description="The first UTC day; 30 days before `end` if left out")
_END = Query(description="The last UTC day; today if left out")


@router.get("/metrics", operation_id="getVersionMetrics", responses=NOT_FOUND_RESPONSE)
async def get_version_metrics(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    version: Annotated[
        list[uuid.UUID] | None,
        Query(
            description="The Agent Versions to show (repeat it for several); every one if left out"
        ),
    ] = None,
    start: Annotated[date | None, _START] = None,
    end: Annotated[date | None, _END] = None,
) -> VersionMetricsOut:
    """Each chosen Agent Version's KPIs over the UTC days `start` to `end` (both inclusive, at
    most 366 days), including today's so far. Only Visitor Conversations count."""
    today = clock.now().astimezone(UTC).date()
    first, last = _range(start, end, today)
    try:
        kpis = await service.version_metrics(
            db, scope, project_id, agent_id, version or [], first, last, today
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.VersionNotFoundError):
        raise not_found() from None
    return VersionMetricsOut(
        agent_id=agent_id, start=first, end=last, versions=[_out(k) for k in kpis]
    )


class CostAmountsOut(BaseModel):
    # In US dollars, at the prices frozen when each reply was made: Visitor replies, Playground
    # replies, and both.
    visitor_usd: Dollars
    playground_usd: Dollars
    total_usd: Dollars


class CostRowOut(CostAmountsOut):
    project_id: uuid.UUID
    project_name: str
    # Set when the cost is broken down by Agent.
    agent_id: uuid.UUID | None
    agent_name: str | None


class OrgCostOut(BaseModel):
    # The UTC days covered, both inclusive.
    start: date
    end: date
    group_by: service.CostGroup
    # One per Project or Agent that replied in the period, most expensive first.
    rows: list[CostRowOut]
    total: CostAmountsOut


@cost_router.get("/cost", operation_id="getOrganisationCost")
async def get_organisation_cost(
    scope: OwnerScope,
    db: Db,
    clock: ClockDep,
    group_by: Annotated[
        service.CostGroup, Query(description="Break the cost down by Project or by Agent")
    ] = service.CostGroup.PROJECT,
    start: Annotated[date | None, _START] = None,
    end: Annotated[date | None, _END] = None,
) -> OrgCostOut:
    """What the Organisation spent over the UTC days `start` to `end` (both inclusive, at most
    366 days), including today's so far, by Project or by Agent. Playground usage is in its own
    column. Owners only."""
    today = clock.now().astimezone(UTC).date()
    first, last = _range(start, end, today)
    lines = await service.org_cost(db, scope, group_by, first, last, today)
    rows = [
        CostRowOut(
            project_id=line.project_id,
            project_name=line.project_name,
            agent_id=line.agent_id,
            agent_name=line.agent_name,
            visitor_usd=line.visitor_usd,
            playground_usd=line.playground_usd,
            total_usd=line.total_usd,
        )
        for line in lines
    ]
    visitor = sum((line.visitor_usd for line in lines), Decimal(0))
    playground = sum((line.playground_usd for line in lines), Decimal(0))
    return OrgCostOut(
        start=first,
        end=last,
        group_by=group_by,
        rows=rows,
        total=CostAmountsOut(
            visitor_usd=visitor, playground_usd=playground, total_usd=visitor + playground
        ),
    )


class TimeSeriesPointOut(BaseModel):
    # The period's first and last UTC day (a whole day, ISO week or month, clipped to the range).
    start: date
    end: date
    # The metric over the period; null when it has no sample (no votes for a rate, say).
    value: float | None
    # The sample size: Conversations, replies, votes or ratings, as the metric counts them.
    n: int


class MarkerVersionOut(BaseModel):
    id: uuid.UUID
    number: int


class LiveHistoryMarkerOut(BaseModel):
    """A change of the Live Version during the range: one Live History entry."""

    occurred_at: datetime
    # The UTC day it happened on, and the start of the point (period) that day is in.
    day: date
    point_start: date
    # publish, revert, bulk_publish or bulk_revert.
    action: str
    # Null for the first publish.
    from_version: MarkerVersionOut | None
    to_version: MarkerVersionOut


class DocumentChangesOut(BaseModel):
    # Documents of the Project added, replaced or processed again during the range.
    changed: int
    # Documents of the Project deleted during the range.
    deleted: int


class TimeSeriesOut(BaseModel):
    agent_id: uuid.UUID
    metric: service.TimeSeriesMetric
    granularity: service.TimeSeriesGranularity
    # The UTC days covered, both inclusive.
    start: date
    end: date
    points: list[TimeSeriesPointOut]
    markers: list[LiveHistoryMarkerOut]
    # The Knowledge Base isn't versioned: changes during the range may confound the series.
    document_changes: DocumentChangesOut


def _version(version: AgentVersion) -> MarkerVersionOut:
    return MarkerVersionOut(id=version.id, number=version.number)


def _point_start(points: list[service.Point], day: date) -> date:
    return max(point.start for point in points if point.start <= day)


@router.get("/time-series", operation_id="getTimeSeries", responses=NOT_FOUND_RESPONSE)
async def get_time_series(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    metric: Annotated[service.TimeSeriesMetric, Query(description="What to measure")],
    granularity: Annotated[
        service.TimeSeriesGranularity, Query(description="One point per day, ISO week or month")
    ] = service.TimeSeriesGranularity.DAY,
    start: Annotated[date | None, _START] = None,
    end: Annotated[date | None, _END] = None,
) -> TimeSeriesOut:
    """One metric of the Agent (every Version together) per period of the UTC days `start` to
    `end` (both inclusive, at most 366 days), including today's so far; with markers where the
    Live Version changed and the Project's Document changes during the range. Only Visitor
    Conversations count."""
    today = clock.now().astimezone(UTC).date()
    first, last = _range(start, end, today)
    try:
        found = await service.time_series(
            db, scope, project_id, agent_id, metric, granularity, first, last, today
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return TimeSeriesOut(
        agent_id=agent_id,
        metric=metric,
        granularity=granularity,
        start=first,
        end=last,
        points=[
            TimeSeriesPointOut(start=p.start, end=p.end, value=p.value, n=p.n) for p in found.points
        ],
        markers=[
            LiveHistoryMarkerOut(
                occurred_at=m.occurred_at,
                day=m.occurred_at.astimezone(UTC).date(),
                point_start=_point_start(found.points, m.occurred_at.astimezone(UTC).date()),
                action=m.action,
                from_version=None if m.from_version is None else _version(m.from_version),
                to_version=_version(m.to_version),
            )
            for m in found.markers
        ],
        document_changes=DocumentChangesOut(
            changed=found.document_changes.changed, deleted=found.document_changes.deleted
        ),
    )
