"""Builds the model gateway with the adapters the settings select."""

import httpx2

from app.core.settings import Settings
from app.crypto.envelope import EnvelopeEncryption
from app.gateway.fakes import FakeModelAdapters
from app.gateway.gateway import ModelGateway
from app.gateway.live import LiveModelAdapters
from app.gateway.ports import ModelAdapters


def build_model_gateway(
    settings: Settings, envelope: EnvelopeEncryption, client: httpx2.AsyncClient
) -> ModelGateway:
    """The gateway with the fake adapters, or the live ones sending calls through ``client``."""
    adapters: ModelAdapters = (
        FakeModelAdapters() if settings.model_gateway == "fake" else LiveModelAdapters(client)
    )
    return ModelGateway(envelope, adapters)
