"""Studio route for Version KPIs: an Agent's Versions' key numbers over a range of UTC days.
Editors and Owners may read them. Playground Conversations never count."""

import uuid
from datetime import UTC, date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.service import AgentNotFoundError
from app.analytics import service
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
    start: Annotated[
        date | None, Query(description="The first UTC day; 30 days before `end` if left out")
    ] = None,
    end: Annotated[date | None, Query(description="The last UTC day; today if left out")] = None,
) -> VersionMetricsOut:
    """Each chosen Agent Version's KPIs over the UTC days `start` to `end` (both inclusive, at
    most 366 days), including today's so far. Only Visitor Conversations count."""
    today = clock.now().astimezone(UTC).date()
    last = end or today
    first = start or last - timedelta(days=DEFAULT_DAYS - 1)
    if first > last:
        raise _bad_range("The start must not be after the end.")
    if (last - first).days >= MAX_DAYS:
        raise _bad_range(f"The range can be at most {MAX_DAYS} days.")
    try:
        kpis = await service.version_metrics(
            db, scope, project_id, agent_id, version or [], first, last, today
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.VersionNotFoundError):
        raise not_found() from None
    return VersionMetricsOut(
        agent_id=agent_id, start=first, end=last, versions=[_out(k) for k in kpis]
    )
