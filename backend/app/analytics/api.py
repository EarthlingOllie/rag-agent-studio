"""Studio routes for Version KPIs and Version comparison: an Agent's Versions' key numbers over a
range of UTC days, and two Versions side by side (also as CSV). Editors and Owners may read
them. Playground Conversations never count."""

import uuid
from datetime import UTC, date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.agents import versions
from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.service import AgentNotFoundError
from app.agents.versions_api import AgentDiffOut, diff_out
from app.analytics import comparison, service
from app.auth.api import Db
from app.playground.api import Dollars
from app.projects.service import ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}", tags=["analytics"]
)

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
        latency=LatencyOut(
            n=usage.latency_histogram.count,
            first_token_p95_ms=usage.first_token_histogram.percentile(0.95),
            total_p95_ms=usage.latency_histogram.percentile(0.95),
        ),
    )


def _bad_range(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


StartQuery = Annotated[
    date | None, Query(description="The first UTC day; 30 days before `end` if left out")
]
EndQuery = Annotated[date | None, Query(description="The last UTC day; today if left out")]


def _days(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    last = end or today
    first = start or last - timedelta(days=DEFAULT_DAYS - 1)
    if first > last:
        raise _bad_range("The start must not be after the end.")
    if (last - first).days >= MAX_DAYS:
        raise _bad_range(f"The range can be at most {MAX_DAYS} days.")
    return first, last


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
    start: StartQuery = None,
    end: EndQuery = None,
) -> VersionMetricsOut:
    """Each chosen Agent Version's KPIs over the UTC days `start` to `end` (both inclusive, at
    most 366 days), including today's so far. Only Visitor Conversations count."""
    today = clock.now().astimezone(UTC).date()
    first, last = _days(start, end, today)
    try:
        kpis = await service.version_metrics(
            db, scope, project_id, agent_id, version or [], first, last, today
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.VersionNotFoundError):
        raise not_found() from None
    return VersionMetricsOut(
        agent_id=agent_id, start=first, end=last, versions=[_out(k) for k in kpis]
    )


class MetricRowOut(BaseModel):
    # A stable name, such as ``thumbs_up_rate``, and how a person reads it.
    metric: str
    label: str
    unit: comparison.Unit
    # Each Version's value; null where it has none (no votes, no ratings, no replies).
    a: float | None
    b: float | None
    # b minus a; null when either side has no value.
    difference: float | None
    # The two values differ (one side having a value and the other none counts).
    changed: bool
    # The Version this metric favours (a higher thumbs-up rate or rating; fewer tokens, lower
    # cost per Conversation, fallback rate and latency); null when it favours neither or they
    # are level. Volumes, totals and interval bounds favour neither.
    better: comparison.Side | None
    # Either Version's sample for this metric is small (fewer than 30).
    low_confidence: bool


class VersionComparisonOut(BaseModel):
    agent_id: uuid.UUID
    # The UTC days covered, both inclusive.
    start: date
    end: date
    a: VersionKpisOut
    b: VersionKpisOut
    # Every metric of the two Versions side by side.
    metrics: list[MetricRowOut]
    # The configuration diff from Version a to Version b, as the Agent diff gives it.
    config_diff: AgentDiffOut


def _number(value: comparison.Value | None) -> float | None:
    return None if value is None else float(value)


def _row_out(row: comparison.MetricRow) -> MetricRowOut:
    return MetricRowOut(
        metric=row.key,
        label=row.label,
        unit=row.unit,
        a=_number(row.a),
        b=_number(row.b),
        difference=_number(row.difference),
        changed=row.changed,
        better=row.better,
        low_confidence=row.low_confidence,
    )


async def _compared(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    a: Annotated[uuid.UUID, Query(description="One of the Agent's Versions: the first side")],
    b: Annotated[uuid.UUID, Query(description="Another of the Agent's Versions: the second side")],
    start: StartQuery = None,
    end: EndQuery = None,
) -> tuple[date, date, comparison.Comparison, versions.ConfigDiff]:
    today = clock.now().astimezone(UTC).date()
    first, last = _days(start, end, today)
    if a == b:
        raise _bad_range("Pick two different Versions to compare.")
    try:
        found = await service.version_metrics(
            db, scope, project_id, agent_id, [a, b], first, last, today
        )
        diff = await versions.diff(db, scope, project_id, agent_id, a, b)
    except (ProjectNotFoundError, AgentNotFoundError, service.VersionNotFoundError):
        raise not_found() from None
    by_id = {kpis.version.id: kpis for kpis in found}
    return first, last, comparison.compare(by_id[a], by_id[b]), diff


Compared = Annotated[
    tuple[date, date, comparison.Comparison, versions.ConfigDiff], Depends(_compared)
]


@router.get("/comparison", operation_id="compareVersions", responses=NOT_FOUND_RESPONSE)
async def compare_versions(agent_id: uuid.UUID, compared: Compared) -> VersionComparisonOut:
    """Versions `a` and `b` side by side over the UTC days `start` to `end` (both inclusive, at
    most 366 days, today's so far included): each Version's KPIs, every metric's difference and
    the Version it favours, and the configuration diff from `a` to `b`. Only Visitor
    Conversations count."""
    first, last, found, diff = compared
    return VersionComparisonOut(
        agent_id=agent_id,
        start=first,
        end=last,
        a=_out(found.a),
        b=_out(found.b),
        metrics=[_row_out(row) for row in found.metrics],
        config_diff=diff_out(diff),
    )


@router.get(
    "/comparison.csv",
    operation_id="exportVersionComparison",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {"schema": {"type": "string"}}}, "description": "CSV"},
        **NOT_FOUND_RESPONSE,
    },
)
async def export_version_comparison(compared: Compared) -> Response:
    """The comparison of Versions `a` and `b` as a CSV download: a row per metric with both
    Versions' values, the difference and the Version it favours."""
    first, last, found, _ = compared
    name = f"comparison-v{found.a.version.number}-v{found.b.version.number}-{first}-to-{last}.csv"
    return Response(
        comparison.to_csv(found),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
