"""The live credential verifier: the cheapest authenticated call each provider offers.

- Anthropic and OpenAI: list models (no tokens spent).
- Voyage: embed one short string with the smallest model.
- Demo: nothing to check; it needs no key.

HTTP answers map to typed failures: 401 is an invalid key, 403 or 404 missing model access,
429 an exhausted quota or rate limit, and anything else (5xx, timeouts, network errors) an
unreachable provider. Anthropic's workspace answers are their own: a key that isn't scoped to one
workspace, sent without ``anthropic-workspace-id``, is 400 (a Workspace ID is required), and a
Workspace ID the key can't use is 404 ``Workspace `<id>` not found.`` (an unknown workspace).
"""

import httpx

from app.credentials.registry import Provider
from app.credentials.verifier import PASSED, CheckFailure, CheckResult

ANTHROPIC_VERSION = "2023-06-01"
WORKSPACE_HEADER = "anthropic-workspace-id"


def _request(provider: Provider, api_key: str, workspace_id: str | None) -> httpx.Request:
    if provider is Provider.ANTHROPIC:
        headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
        if workspace_id is not None:
            headers[WORKSPACE_HEADER] = workspace_id
        return httpx.Request(
            "GET", "https://api.anthropic.com/v1/models", params={"limit": "1"}, headers=headers
        )
    bearer = {"Authorization": f"Bearer {api_key}"}
    if provider is Provider.OPENAI:
        return httpx.Request("GET", "https://api.openai.com/v1/models", headers=bearer)
    if provider is Provider.VOYAGE:
        return httpx.Request(
            "POST",
            "https://api.voyageai.com/v1/embeddings",
            headers=bearer,
            json={"input": ["ping"], "model": "voyage-3.5-lite"},
        )
    raise ValueError(f"{provider} credentials are not checked with an API key")


def _message(response: httpx.Response) -> str:
    """The provider's error message, or nothing when the body isn't the error shape."""
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return message if isinstance(message, str) else ""


def _anthropic_workspace(response: httpx.Response) -> CheckFailure | None:
    """The workspace failure an Anthropic 400 or 404 reports, by its documented message."""
    message = _message(response)
    if response.status_code == 400 and "not scoped to a workspace" in message:
        return CheckFailure.WORKSPACE_REQUIRED
    if (response.status_code == 400 and "must be a valid workspace ID" in message) or (
        response.status_code == 404 and message.startswith("Workspace `")
    ):
        return CheckFailure.UNKNOWN_WORKSPACE
    return None


def _result(status_code: int) -> CheckResult:
    if status_code < 300:
        return PASSED
    if status_code == 401:
        return CheckResult(CheckFailure.INVALID_KEY)
    if status_code in (403, 404):
        return CheckResult(CheckFailure.MISSING_MODEL_ACCESS)
    if status_code == 429:
        return CheckResult(CheckFailure.QUOTA_EXCEEDED)
    return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)


class HttpCredentialVerifier:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def check(
        self, provider: Provider, api_key: str, *, workspace_id: str | None = None
    ) -> CheckResult:
        if provider is Provider.DEMO:
            return PASSED  # nothing to call: the demo model is built offline
        try:
            response = await self._client.send(_request(provider, api_key, workspace_id))
        except httpx.HTTPError:
            return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)
        if provider is Provider.ANTHROPIC and response.status_code in (400, 404):
            failure = _anthropic_workspace(response)
            if failure is not None:
                return CheckResult(failure)
        return _result(response.status_code)
