"""Builds the credential verifier the settings select."""

import httpx

from app.core.settings import Settings
from app.credentials.http_verifier import HttpCredentialVerifier
from app.credentials.verifier import CredentialVerifier, FakeCredentialVerifier


def build_verifier(settings: Settings, client: httpx.AsyncClient) -> CredentialVerifier:
    """The fake verifier, or the live one sending its calls through ``client``."""
    if settings.credential_verifier == "fake":
        return FakeCredentialVerifier()
    return HttpCredentialVerifier(client)
