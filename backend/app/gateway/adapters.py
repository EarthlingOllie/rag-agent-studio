"""Builds the model gateway with the adapters the settings select."""

from datetime import timedelta
from functools import partial

import httpx2

from app.core.clock import SystemClock
from app.core.settings import Settings
from app.credentials.bedrock_verifier import AssumedRoleSessions, boto3_client
from app.crypto.envelope import EnvelopeEncryption
from app.gateway.fakes import FakeModelAdapters
from app.gateway.gateway import ModelGateway
from app.gateway.live import BedrockClients, LiveModelAdapters
from app.gateway.ports import ModelAdapters


def build_model_gateway(
    settings: Settings, envelope: EnvelopeEncryption, client: httpx2.AsyncClient
) -> ModelGateway:
    """The gateway with the fake adapters, or the live ones: HTTP providers through ``client``,
    Bedrock through boto3, assuming Owners' roles with the platform's own AWS identity."""
    if settings.model_gateway == "fake":
        return ModelGateway(envelope, FakeModelAdapters())
    clients = partial(boto3_client, timeout_seconds=settings.model_timeout_seconds)
    sessions = AssumedRoleSessions(
        clients("sts", settings.bedrock_sts_region, None),
        SystemClock(),
        refresh_before=timedelta(seconds=settings.bedrock_session_refresh_seconds),
    )
    adapters: ModelAdapters = LiveModelAdapters(client, BedrockClients(sessions, clients))
    return ModelGateway(envelope, adapters)
