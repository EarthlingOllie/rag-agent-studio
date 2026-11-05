"""FastAPI application. Settings are loaded and validated when the app starts."""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import logfire
from fastapi import FastAPI
from opentelemetry.sdk.trace import SpanProcessor
from redis.asyncio import Redis

from app.api import health
from app.audit import api as audit_api
from app.auth import account_api, mfa_api
from app.auth import api as auth_api
from app.core.clock import SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.logs import configure_logging
from app.core.settings import load_settings
from app.core.telemetry import configure_telemetry, flush_telemetry, instrument_engine
from app.crypto.adapters import build_envelope
from app.mail.factory import build_mailer
from app.tenancy import api as tenancy_api
from app.tenancy import invites_api
from app.worker.celery_app import configure_celery

logger = logging.getLogger(__name__)


def _lifespan(
    extra_span_processors: Sequence[SpanProcessor],
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("api")
        settings = load_settings()
        configure_telemetry(settings, "api", extra_span_processors=extra_span_processors)
        app.state.settings = settings
        app.state.envelope = build_envelope(settings)
        configure_celery(settings)
        app.state.engine = create_engine(settings)
        instrument_engine(app.state.engine)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        app.state.redis = Redis.from_url(str(settings.redis_url))
        app.state.clock = SystemClock()
        app.state.mailer = build_mailer(settings)
        logger.info("API started", extra={"environment": settings.environment})
        try:
            yield
        finally:
            await app.state.redis.aclose()
            await app.state.engine.dispose()
            flush_telemetry()

    return lifespan


def create_app(*, extra_span_processors: Sequence[SpanProcessor] = ()) -> FastAPI:
    """Build the API. ``extra_span_processors`` receive spans next to the configured exporter."""
    app = FastAPI(
        title="RAG Agent Studio API", version="0.1.0", lifespan=_lifespan(extra_span_processors)
    )
    app.include_router(health.router)
    app.include_router(auth_api.router)
    app.include_router(mfa_api.router)
    app.include_router(account_api.router)
    app.include_router(tenancy_api.router)
    app.include_router(audit_api.router)
    app.include_router(invites_api.owner_router)
    app.include_router(invites_api.router)
    # Headers are captured for debugging; the scrubbing processor redacts the sensitive ones.
    logfire.instrument_fastapi(app, capture_headers=True)
    return app


app = create_app()
