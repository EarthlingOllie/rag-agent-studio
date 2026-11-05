"""FastAPI application. Settings are loaded and validated when the app starts."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api import health
from app.core.db import create_engine
from app.core.settings import load_settings
from app.worker.celery_app import configure_celery


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    app.state.settings = settings
    configure_celery(settings)
    app.state.engine = create_engine(settings)
    app.state.redis = Redis.from_url(str(settings.redis_url))
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Agent Studio API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
