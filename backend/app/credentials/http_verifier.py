"""The live credential verifier: the cheapest authenticated call each provider offers.

- Anthropic and OpenAI: list models (no tokens spent).
- Voyage: embed one short string with the smallest model.
- Demo: nothing to check; it needs no key.

HTTP answers map to typed failures: 401 is an invalid key, 403 or 404 missing model access,
429 an exhausted quota or rate limit, and anything else (5xx, timeouts, network errors) an
unreachable provider.
"""

import httpx

from app.credentials.registry import Provider
from app.credentials.verifier import PASSED, CheckFailure, CheckResult

ANTHROPIC_VERSION = "2023-06-01"


def _request(provider: Provider, api_key: str) -> httpx.Request:
    if provider is Provider.ANTHROPIC:
        return httpx.Request(
            "GET",
            "https://api.anthropic.com/v1/models",
            params={"limit": "1"},
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
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
        return _result(response.status_code)
