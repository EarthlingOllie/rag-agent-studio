"""The live credential verifier: the cheapest authenticated call each provider offers.

- Anthropic and OpenAI: list models (no tokens spent).
- Voyage: embed one short string with the smallest model.
- ElevenLabs: list one Agent, which proves the key works and may use the Agents API that
  Calls are set up through.
- Demo: nothing to check; it needs no key.

HTTP answers map to typed failures: 401 is an invalid key, 403 or 404 missing model access,
429 an exhausted quota or rate limit, and anything else (5xx, timeouts, network errors) an
unreachable provider. ElevenLabs answers every unusable key with a 401 (or a 403) and says
why in ``detail.status``: an exhausted quota is a quota failure, anything else (a wrong key, or
a key whose permissions leave out ElevenLabs Agents) an invalid key.
"""

import httpx

from app.credentials.registry import Provider
from app.credentials.verifier import PASSED, CheckFailure, CheckResult

ANTHROPIC_VERSION = "2023-06-01"
ELEVENLABS_AGENTS = "https://api.elevenlabs.io/v1/convai/agents"


def _request(provider: Provider, api_key: str) -> httpx.Request:
    if provider is Provider.ANTHROPIC:
        return httpx.Request(
            "GET",
            "https://api.anthropic.com/v1/models",
            params={"limit": "1"},
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
        )
    if provider is Provider.ELEVENLABS:
        return httpx.Request(
            "GET", ELEVENLABS_AGENTS, params={"page_size": "1"}, headers={"xi-api-key": api_key}
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


def _elevenlabs_status(response: httpx.Response) -> object:
    """ElevenLabs' reason for refusing a key (``detail.status``), or None."""
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail.get("status") if isinstance(detail, dict) else None


def _elevenlabs_result(response: httpx.Response) -> CheckResult:
    """Never missing model access: ElevenLabs has no models, and refuses a key without
    ElevenLabs Agents permissions as it refuses a wrong one."""
    code = response.status_code
    if code in (401, 403):
        if _elevenlabs_status(response) == "quota_exceeded":
            return CheckResult(CheckFailure.QUOTA_EXCEEDED)
        return CheckResult(CheckFailure.INVALID_KEY)
    if code < 300:
        return PASSED
    if code == 429:
        return CheckResult(CheckFailure.QUOTA_EXCEEDED)
    return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)


class HttpCredentialVerifier:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        if provider is Provider.DEMO:
            return PASSED  # nothing to call: the demo model is built offline
        try:
            response = await self._client.send(_request(provider, api_key))
        except httpx.HTTPError:
            return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)
        if provider is Provider.ELEVENLABS:
            return _elevenlabs_result(response)
        return _result(response.status_code)
