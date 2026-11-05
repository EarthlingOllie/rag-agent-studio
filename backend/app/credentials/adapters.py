"""Builds the credential verifier the settings select."""

from datetime import timedelta
from functools import partial

import httpx

from app.core.clock import Clock
from app.core.settings import Settings
from app.credentials.bedrock_verifier import AssumedRoleSessions, BedrockVerifier, boto3_client
from app.credentials.http_verifier import HttpCredentialVerifier
from app.credentials.registry import Provider
from app.credentials.verifier import (
    BedrockAccess,
    CheckResult,
    CredentialVerifier,
    FakeCredentialVerifier,
)


class LiveCredentialVerifier:
    """Checks API keys over HTTP and Bedrock credentials through STS and Bedrock."""

    def __init__(self, api_keys: HttpCredentialVerifier, bedrock: BedrockVerifier) -> None:
        self.api_keys = api_keys
        self.bedrock = bedrock

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        return await self.api_keys.check(provider, api_key)

    async def check_bedrock(self, access: BedrockAccess) -> CheckResult:
        return await self.bedrock.check(access)


def build_verifier(
    settings: Settings, client: httpx.AsyncClient, clock: Clock
) -> CredentialVerifier:
    """The fake verifier, or the live one: API keys through ``client``, Bedrock through boto3
    with the platform's own AWS identity."""
    if settings.credential_verifier == "fake":
        return FakeCredentialVerifier()
    clients = partial(boto3_client, timeout_seconds=settings.credential_check_timeout_seconds)
    sessions = AssumedRoleSessions(
        clients("sts", settings.bedrock_sts_region, None),
        clock,
        refresh_before=timedelta(seconds=settings.bedrock_session_refresh_seconds),
    )
    bedrock = BedrockVerifier(sessions, clients, sts_region=settings.bedrock_sts_region)
    return LiveCredentialVerifier(HttpCredentialVerifier(client), bedrock)
