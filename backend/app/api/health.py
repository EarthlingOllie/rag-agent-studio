import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.settings import Settings
from app.worker.tasks import health_check

CheckStatus = Literal["ok", "error"]

WORKER_POLL_INTERVAL_SECONDS = 0.05

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
    except Exception:
        return "error"
    return "ok"


async def _check_redis(redis: "Redis") -> CheckStatus:
    try:
        await redis.ping()
    except Exception:
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


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get(
    "/worker",
    response_model=WorkerHealthResponse,
    responses={503: {"model": WorkerHealthResponse, "description": "No worker replied in time, or the health task failed"}},
    operation_id="getWorkerHealth",
)
async def get_worker_health(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkerHealthResponse:
    """Enqueue the worker health task and wait for the worker's reply."""
    # Poll rather than block on AsyncResult.get, so no pub/sub subscription is held per request.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.worker_health_timeout_seconds
    result = await run_in_threadpool(health_check.delay)
    while not await run_in_threadpool(result.ready):
        if loop.time() >= deadline:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return WorkerHealthResponse(status="error", reply=None)
        await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)
    # ready() is also true for a failed task; only a successful one counts as a round trip.
    if not await run_in_threadpool(result.successful):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return WorkerHealthResponse(status="error", reply=None)
    return WorkerHealthResponse(status="ok", reply=str(result.result))
