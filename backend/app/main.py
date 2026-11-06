"""FastAPI application. Settings are loaded and validated when the app starts."""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
import httpx2
import logfire
from fastapi import APIRouter, FastAPI
from opentelemetry.sdk.trace import SpanProcessor
from redis.asyncio import Redis

from app.agents import api as agents_api
from app.agents import bulk_api
from app.agents import versions_api as agent_versions_api
from app.agents.validation import agent_references
from app.api import health
from app.audit import api as audit_api
from app.auth import account_api, mfa_api
from app.auth import api as auth_api
from app.core.clock import SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.logs import configure_logging
from app.core.settings import load_settings
from app.core.telemetry import configure_telemetry, flush_telemetry, instrument_engine
from app.credentials import api as credentials_api
from app.credentials.adapters import build_verifier
from app.credentials.references import ReferenceRegistry
from app.crypto.adapters import build_envelope
from app.default_model import api as default_model_api
from app.default_model.service import default_model_references
from app.documents import api as documents_api
from app.documents.ports import build_ports, install_ports
from app.gateway.adapters import build_model_gateway
from app.mail.factory import build_mailer
from app.playground import api as playground_api
from app.pricing import api as pricing_api
from app.projects import api as projects_api
from app.projects import embedding_api, instructions_api
from app.projects.embedding import project_embedding_references
from app.tags import api as tags_api
from app.tenancy import api as tenancy_api
from app.tenancy import invites_api, members_api, switcher_api
from app.theme import api as theme_api
from app.worker.celery_app import configure_celery

logger = logging.getLogger(__name__)

# Every API router. Tests read their routes to check each one's policy dependency.
ROUTERS: Sequence[APIRouter] = (
    health.router,
    auth_api.router,
    mfa_api.router,
    account_api.router,
    tenancy_api.router,
    audit_api.router,
    invites_api.owner_router,
    invites_api.router,
    members_api.router,
    switcher_api.router,
    credentials_api.router,
    credentials_api.providers_router,
    default_model_api.router,
    pricing_api.router,
    theme_api.router,
    theme_api.fonts_router,
    projects_api.router,
    embedding_api.router,
    instructions_api.router,
    documents_api.router,
    tags_api.router,
    agents_api.router,
    agent_versions_api.router,
    bulk_api.router,
    playground_api.router,
)


def _lifespan(
    extra_span_processors: Sequence[SpanProcessor],
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("api")
        settings = load_settings()
        configure_telemetry(settings, "api", extra_span_processors=extra_span_processors)
        app.state.settings = settings
        app.state.clock = SystemClock()
        app.state.envelope = build_envelope(settings)
        configure_celery(settings)
        app.state.engine = create_engine(settings)
        instrument_engine(app.state.engine)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        app.state.redis = Redis.from_url(str(settings.redis_url))
        app.state.clock = SystemClock()
        app.state.mailer = build_mailer(settings)
        app.state.provider_http = httpx.AsyncClient(
            timeout=settings.credential_check_timeout_seconds
        )
        app.state.credential_verifier = build_verifier(
            settings, app.state.provider_http, app.state.clock
        )
        # Pydantic AI's provider clients take httpx2 clients; every model call shares this one.
        app.state.model_http = httpx2.AsyncClient(timeout=settings.model_timeout_seconds)
        app.state.model_gateway = build_model_gateway(
            settings, app.state.envelope, app.state.model_http
        )
        # Ingestion tasks enqueued from here run in the worker; in tests they run eagerly in
        # this process and use these same adapters.
        app.state.ingestion = build_ports(settings, app.state.envelope)
        install_ports(app.state.ingestion)
        if settings.object_store_create_bucket:
            await app.state.ingestion.object_store.prepare()
        logger.info("API started", extra={"environment": settings.environment})
        try:
            yield
        finally:
            await app.state.model_http.aclose()
            await app.state.provider_http.aclose()
            await app.state.redis.aclose()
            await app.state.engine.dispose()
            flush_telemetry()

    return lifespan


def create_app(*, extra_span_processors: Sequence[SpanProcessor] = ()) -> FastAPI:
    """Build the API. ``extra_span_processors`` receive spans next to the configured exporter."""
    app = FastAPI(
        title="RAG Agent Studio API", version="0.1.0", lifespan=_lifespan(extra_span_processors)
    )
    # Consumers of Provider Credentials register their "who references me" sources here.
    app.state.credential_references = ReferenceRegistry()
    app.state.credential_references.register(default_model_references)
    app.state.credential_references.register(agent_references)
    app.state.credential_references.register(project_embedding_references)
    for router in ROUTERS:
        app.include_router(router)
    # Headers are captured for debugging; the scrubbing processor redacts the sensitive ones.
    logfire.instrument_fastapi(app, capture_headers=True)
    return app


app = create_app()
