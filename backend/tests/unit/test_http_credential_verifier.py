"""The live credential verifier against stubbed provider endpoints.

No real provider is called: ``httpx.MockTransport`` answers with responses shaped like the
providers' recorded answers, and each test checks the request the adapter sent (URL,
authentication header, body) and the typed result it made of the answer.
"""

import json

import httpx
import pytest

from app.core.clock import SystemClock
from app.core.settings import Settings
from app.credentials.adapters import LiveCredentialVerifier, build_verifier
from app.credentials.http_verifier import HttpCredentialVerifier
from app.credentials.registry import Provider
from app.credentials.verifier import (
    CheckFailure,
    CheckResult,
    FakeCredentialVerifier,
)

KEY = "sk-test-only-0000000000000000"

# Shapes of the providers' answers, trimmed from their API references.
ANTHROPIC_MODELS = {"data": [{"type": "model", "id": "claude-sonnet-4-5"}], "has_more": True}
OPENAI_MODELS = {"object": "list", "data": [{"id": "gpt-4.1", "object": "model"}]}
VOYAGE_EMBEDDING = {
    "object": "list",
    "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}],
    "model": "voyage-3.5-lite",
    "usage": {"total_tokens": 1},
}
UNAUTHORISED = {"error": {"type": "authentication_error", "message": "invalid x-api-key"}}


def _verifier(status: int, body: object, seen: list[httpx.Request]) -> HttpCredentialVerifier:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return HttpCredentialVerifier(httpx.AsyncClient(transport=httpx.MockTransport(answer)))


async def test_anthropic_is_checked_by_listing_models_with_the_key_header() -> None:
    seen: list[httpx.Request] = []

    result = await _verifier(200, ANTHROPIC_MODELS, seen).check(Provider.ANTHROPIC, KEY)

    assert result == CheckResult()
    (request,) = seen
    assert (request.method, str(request.url)) == (
        "GET",
        "https://api.anthropic.com/v1/models?limit=1",
    )
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2023-06-01"


async def test_openai_is_checked_by_listing_models_with_a_bearer_token() -> None:
    seen: list[httpx.Request] = []

    result = await _verifier(200, OPENAI_MODELS, seen).check(Provider.OPENAI, KEY)

    assert result.passed
    (request,) = seen
    assert (request.method, str(request.url)) == ("GET", "https://api.openai.com/v1/models")
    assert request.headers["authorization"] == f"Bearer {KEY}"


async def test_voyage_is_checked_with_a_one_token_embedding() -> None:
    seen: list[httpx.Request] = []

    result = await _verifier(200, VOYAGE_EMBEDDING, seen).check(Provider.VOYAGE, KEY)

    assert result.passed
    (request,) = seen
    assert (request.method, str(request.url)) == ("POST", "https://api.voyageai.com/v1/embeddings")
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {"input": ["ping"], "model": "voyage-3.5-lite"}


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (401, CheckFailure.INVALID_KEY),
        (403, CheckFailure.MISSING_MODEL_ACCESS),
        (404, CheckFailure.MISSING_MODEL_ACCESS),
        (429, CheckFailure.QUOTA_EXCEEDED),
        (400, CheckFailure.PROVIDER_UNREACHABLE),
        (500, CheckFailure.PROVIDER_UNREACHABLE),
        (529, CheckFailure.PROVIDER_UNREACHABLE),
    ],
)
@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI, Provider.VOYAGE])
async def test_provider_errors_become_typed_failures(
    status: int, failure: CheckFailure, provider: Provider
) -> None:
    result = await _verifier(status, UNAUTHORISED, []).check(provider, KEY)

    assert result == CheckResult(failure)
    assert not result.passed


async def test_a_network_error_is_an_unreachable_provider() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    verifier = HttpCredentialVerifier(httpx.AsyncClient(transport=httpx.MockTransport(fail)))

    assert await verifier.check(Provider.OPENAI, KEY) == CheckResult(
        CheckFailure.PROVIDER_UNREACHABLE
    )


async def test_bedrock_is_not_checked_with_an_api_key() -> None:
    with pytest.raises(ValueError, match="not checked with an API key"):
        await _verifier(200, {}, []).check(Provider.BEDROCK, KEY)


def _settings(**values: str) -> Settings:
    base = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "local_key_wrapper_key": "dGVzdC1vbmx5LWxvY2FsLWtleS13cmFwcGVyLWtleSE=",
    }
    return Settings.model_validate(base | values)


@pytest.mark.parametrize(
    ("setting", "adapter"),
    [("live", LiveCredentialVerifier), ("fake", FakeCredentialVerifier)],
)
async def test_settings_select_the_verifier(setting: str, adapter: type[object]) -> None:
    async with httpx.AsyncClient() as client:
        verifier = build_verifier(_settings(credential_verifier=setting), client, SystemClock())

    assert isinstance(verifier, adapter)


def test_the_live_verifier_is_the_default() -> None:
    assert _settings().credential_verifier == "live"
