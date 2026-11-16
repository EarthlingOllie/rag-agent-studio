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


WORKSPACE = "wrkspc_01JwQvzr7rXLA5AGx3HKfFUJ"
# Anthropic's documented workspace answers (Authentication > Select a workspace).
NOT_SCOPED = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "This API key is not scoped to a workspace, so this request must include the "
        "anthropic-workspace-id header with the ID of the workspace to use. Add the header, or "
        "use an API key that is scoped to a workspace.",
    },
}
MALFORMED_WORKSPACE = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "anthropic-workspace-id header must be a valid workspace ID.",
    },
}
UNKNOWN_WORKSPACE = {
    "type": "error",
    "error": {"type": "not_found_error", "message": f"Workspace `{WORKSPACE}` not found."},
}


async def test_an_anthropic_key_is_checked_in_the_workspace_it_names() -> None:
    seen: list[httpx.Request] = []

    verifier = _verifier(200, ANTHROPIC_MODELS, seen)
    result = await verifier.check(Provider.ANTHROPIC, KEY, workspace_id=WORKSPACE)

    assert result.passed
    (request,) = seen
    assert request.headers["anthropic-workspace-id"] == WORKSPACE
    assert request.headers["x-api-key"] == KEY


async def test_without_a_workspace_no_workspace_header_is_sent() -> None:
    seen: list[httpx.Request] = []

    await _verifier(200, ANTHROPIC_MODELS, seen).check(Provider.ANTHROPIC, KEY)

    (request,) = seen
    assert "anthropic-workspace-id" not in request.headers


@pytest.mark.parametrize(
    ("status", "body", "failure"),
    [
        (400, NOT_SCOPED, CheckFailure.WORKSPACE_REQUIRED),
        (400, MALFORMED_WORKSPACE, CheckFailure.UNKNOWN_WORKSPACE),
        (404, UNKNOWN_WORKSPACE, CheckFailure.UNKNOWN_WORKSPACE),
        # Other 400s and 404s keep their usual meaning.
        (400, UNAUTHORISED, CheckFailure.PROVIDER_UNREACHABLE),
        (
            404,
            {"error": {"type": "not_found_error", "message": "Not found"}},
            CheckFailure.MISSING_MODEL_ACCESS,
        ),
        (404, {"error": "not found"}, CheckFailure.MISSING_MODEL_ACCESS),
        (404, {"error": {"message": 404}}, CheckFailure.MISSING_MODEL_ACCESS),
        (404, ["not", "an", "object"], CheckFailure.MISSING_MODEL_ACCESS),
    ],
)
async def test_anthropics_workspace_answers_become_workspace_failures(
    status: int, body: object, failure: CheckFailure
) -> None:
    verifier = _verifier(status, body, [])

    assert await verifier.check(Provider.ANTHROPIC, KEY) == CheckResult(failure)


async def test_an_error_page_that_isnt_json_keeps_its_usual_meaning() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<html>Not found</html>")

    verifier = HttpCredentialVerifier(httpx.AsyncClient(transport=httpx.MockTransport(answer)))

    assert await verifier.check(Provider.ANTHROPIC, KEY) == CheckResult(
        CheckFailure.MISSING_MODEL_ACCESS
    )


async def test_the_workspace_answers_are_read_only_from_anthropic() -> None:
    verifier = _verifier(400, NOT_SCOPED, [])

    assert await verifier.check(Provider.OPENAI, KEY) == CheckResult(
        CheckFailure.PROVIDER_UNREACHABLE
    )


async def test_the_live_verifier_passes_the_workspace_to_the_api_key_check() -> None:
    seen: list[httpx.Request] = []
    async with httpx.AsyncClient() as client:
        live = build_verifier(_settings(), client, SystemClock())
    assert isinstance(live, LiveCredentialVerifier)
    live.api_keys = _verifier(200, ANTHROPIC_MODELS, seen)

    assert (await live.check(Provider.ANTHROPIC, KEY, workspace_id=WORKSPACE)).passed
    (request,) = seen
    assert request.headers["anthropic-workspace-id"] == WORKSPACE


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


async def test_the_demo_provider_passes_without_calling_anyone() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        pytest.fail("The demo provider has nobody to call")

    verifier = HttpCredentialVerifier(httpx.AsyncClient(transport=httpx.MockTransport(fail)))

    assert await verifier.check(Provider.DEMO, "demo-no-key-needed") == CheckResult()


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
