import asyncio
import logging
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.clock import Clock, get_clock
from app.core.settings import Settings
from app.worker.tasks import health_check

CheckStatus = Literal["ok", "error"]

WORKER_POLL_INTERVAL_SECONDS = 0.05

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


class HealthChecks(BaseModel):
    database: CheckStatus
    redis: CheckStatus


class HealthResponse(BaseModel):
    status: CheckStatus
    checks: HealthChecks


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


def get_redis(request: Request) -> "Redis":
    redis: Redis = request.app.state.redis
    return redis


async def _check_database(engine: AsyncEngine) -> CheckStatus:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Database health check failed", extra={"error": type(exc).__name__})
        return "error"
    return "ok"


async def _check_redis(redis: "Redis") -> CheckStatus:
    try:
        await redis.ping()
    except Exception as exc:
        logger.warning("Redis health check failed", extra={"error": type(exc).__name__})
        return "error"
    return "ok"


@router.get(
    "",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "A dependency is unreachable"}},
    operation_id="getHealth",
)
async def get_health(
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    redis: Annotated["Redis", Depends(get_redis)],
) -> HealthResponse:
    checks = HealthChecks(database=await _check_database(engine), redis=await _check_redis(redis))
    healthy = checks.database == "ok" and checks.redis == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "error", checks=checks)


class WorkerHealthResponse(BaseModel):
    status: CheckStatus
    reply: str | None


class WorkerProbe:
    """Checks the worker for every caller at once. The route is unauthenticated, so each call
    must not enqueue its own task: callers that arrive while a check runs share it, and its
    answer is reused for ``cache_seconds`` (AUTH-F2). One per API process."""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.worker_health_timeout_seconds
        self._cache_for = timedelta(seconds=settings.worker_health_cache_seconds)
        self._running: asyncio.Future[WorkerHealthResponse] | None = None
        self._latest: tuple[datetime, WorkerHealthResponse] | None = None

    async def check(self, clock: Clock) -> WorkerHealthResponse:
        if self._latest is not None and clock.now() - self._latest[0] < self._cache_for:
            return self._latest[1]
        if self._running is None:
            self._running = asyncio.ensure_future(self._probe(clock))
        # Shielded: a caller that goes away must not cancel the check the others wait for.
        return await asyncio.shield(self._running)

    async def _probe(self, clock: Clock) -> WorkerHealthResponse:
        try:
            reply = await self._round_trip()
            self._latest = (clock.now(), reply)
            return reply
        finally:
            self._running = None

    async def _round_trip(self) -> WorkerHealthResponse:
        """Enqueue the worker health task and wait for the worker's reply."""
        # Poll rather than block on AsyncResult.get, so no pub/sub subscription is held.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        result = await run_in_threadpool(health_check.delay)
        while not await run_in_threadpool(result.ready):
            if loop.time() >= deadline:
                return WorkerHealthResponse(status="error", reply=None)
            await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)
        # ready() is also true for a failed task; only a successful one counts as a round trip.
        if not await run_in_threadpool(result.successful):
            return WorkerHealthResponse(status="error", reply=None)
        return WorkerHealthResponse(status="ok", reply=str(result.result))


def get_worker_probe(request: Request) -> WorkerProbe:
    probe: WorkerProbe = request.app.state.worker_probe
    return probe


@router.get(
    "/worker",
    response_model=WorkerHealthResponse,
    responses={
        503: {
            "model": WorkerHealthResponse,
            "description": "No worker replied in time, or the health task failed",
        }
    },
    operation_id="getWorkerHealth",
)
async def get_worker_health(
    response: Response,
    probe: Annotated[WorkerProbe, Depends(get_worker_probe)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> WorkerHealthResponse:
    """The worker's reply to a health task: a fresh round trip, or one at most a few seconds old."""
    health = await probe.check(clock)
    if health.status == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health
