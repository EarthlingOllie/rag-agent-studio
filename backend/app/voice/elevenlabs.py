"""The ElevenLabs voice layer: the production adapter behind the voice layer port (ADR-0019).

Each operation is one or a few calls to the ElevenLabs Agents API with the Organisation's key
(``xi-api-key``):

- A remote agent is an ElevenLabs agent whose LLM is ``custom-llm``: our turn endpoint, with the
  per-Agent secret as its API key and the extra-body override allowed, so the Call token the
  widget passes reaches the turn endpoint. ElevenLabs keeps a custom LLM's key only as a
  workspace secret, so the adapter stores the secret first and points the agent at it; updating
  reads the agent to find that secret, and removing deletes both.
- Voices come from ``/v2/voices``, page by page.
- Starting a Call asks for a WebRTC conversation token, which the browser joins with.

A remote agent or secret already gone counts as removed, and one gone before an update is made
again. Every other refusal, an answer that isn't JSON, and a network failure raise
``VoiceLayerError``. Each operation opens its own HTTP client, so the adapter works from any
event loop (the API's, or a worker task's).
"""

import contextlib
from typing import Any

import httpx

from app.voice.port import CallJoin, RemoteAgentSpec, Voice, VoiceLayerError

BASE_URL = "https://api.elevenlabs.io"
# The most voices ElevenLabs returns per page, and the most pages read.
VOICES_PAGE_SIZE = 100
VOICES_MAX_PAGES = 20


class _GoneError(Exception):
    """ElevenLabs answered 404: the remote agent or secret no longer exists."""


def _secret_name(spec: RemoteAgentSpec) -> str:
    return f"{spec.name} turn endpoint key"


def _agent_body(spec: RemoteAgentSpec, secret_id: str) -> dict[str, Any]:
    return {
        "name": spec.name,
        "conversation_config": {
            "agent": {
                "first_message": spec.spoken_greeting,
                "language": spec.language,
                # No prompt of its own: every reply comes from the turn endpoint.
                "prompt": {
                    "prompt": "",
                    "llm": "custom-llm",
                    "custom_llm": {"url": spec.llm_url, "api_key": {"secret_id": secret_id}},
                },
            },
            "tts": {"voice_id": spec.voice_id},
        },
        "platform_settings": {"overrides": {"custom_llm_extra_body": spec.extra_body}},
    }


def _secret_of(agent: dict[str, Any]) -> str | None:
    """The workspace secret a remote agent presents to its custom LLM, if it has one."""
    prompt = agent.get("conversation_config", {}).get("agent", {}).get("prompt", {})
    api_key = (prompt.get("custom_llm") or {}).get("api_key") or {}
    return api_key.get("secret_id")


class ElevenLabsVoiceLayer:
    def __init__(
        self, timeout_seconds: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._timeout = timeout_seconds
        # Tests replay recorded exchanges through it; production uses httpx's own.
        self._transport = transport

    async def _call(
        self,
        api_key: str,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        """The answer's JSON (None for an empty one). Raises ``_GoneError`` on 404 and
        ``VoiceLayerError`` on any other failure."""
        try:
            async with httpx.AsyncClient(
                base_url=BASE_URL, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(
                    method, path, json=json, params=params, headers={"xi-api-key": api_key}
                )
        except httpx.HTTPError as error:
            raise VoiceLayerError(f"ElevenLabs couldn't be reached: {error}") from None
        if response.status_code == httpx.codes.NOT_FOUND:
            raise _GoneError
        if not response.is_success:
            raise VoiceLayerError(f"ElevenLabs refused {method} {path}: {response.status_code}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise VoiceLayerError(f"ElevenLabs answered {method} {path} without JSON") from None

    async def _store_secret(self, api_key: str, spec: RemoteAgentSpec) -> str:
        body = {"type": "new", "name": _secret_name(spec), "value": spec.llm_secret}
        stored = await self._call(api_key, "POST", "/v1/convai/secrets", json=body)
        return str(stored["secret_id"])

    async def _forget_secret(self, api_key: str, secret_id: str) -> None:
        with contextlib.suppress(_GoneError):
            await self._call(api_key, "DELETE", f"/v1/convai/secrets/{secret_id}")

    async def _update_secret(self, api_key: str, spec: RemoteAgentSpec, secret_id: str) -> bool:
        """Sets the stored secret's value; False when it is gone."""
        body = {"type": "update", "name": _secret_name(spec), "value": spec.llm_secret}
        try:
            await self._call(api_key, "PATCH", f"/v1/convai/secrets/{secret_id}", json=body)
        except _GoneError:
            return False
        return True

    async def _create_agent(self, api_key: str, spec: RemoteAgentSpec) -> str:
        secret_id = await self._store_secret(api_key, spec)
        try:
            created = await self._call(
                api_key, "POST", "/v1/convai/agents/create", json=_agent_body(spec, secret_id)
            )
        except (VoiceLayerError, _GoneError):
            # Nothing points at the secret now; don't leave it in the account.
            await self._forget_secret(api_key, secret_id)
            raise VoiceLayerError("ElevenLabs refused to create the remote agent") from None
        return str(created["agent_id"])

    async def set_up_agent(
        self, api_key: str, spec: RemoteAgentSpec, *, remote_agent_id: str | None
    ) -> str:
        if remote_agent_id is None:
            return await self._create_agent(api_key, spec)
        path = f"/v1/convai/agents/{remote_agent_id}"
        try:
            agent = await self._call(api_key, "GET", path)
        except _GoneError:
            return await self._create_agent(api_key, spec)
        secret_id = _secret_of(agent)
        if secret_id is None or not await self._update_secret(api_key, spec, secret_id):
            secret_id = await self._store_secret(api_key, spec)
        try:
            await self._call(api_key, "PATCH", path, json=_agent_body(spec, secret_id))
        except _GoneError:
            raise VoiceLayerError("The remote agent was deleted while it was updated") from None
        return remote_agent_id

    async def remove_agent(self, api_key: str, remote_agent_id: str) -> None:
        path = f"/v1/convai/agents/{remote_agent_id}"
        try:
            secret_id = _secret_of(await self._call(api_key, "GET", path))
            await self._call(api_key, "DELETE", path)
        except _GoneError:
            return
        if secret_id is not None:
            await self._forget_secret(api_key, secret_id)

    async def list_voices(self, api_key: str) -> list[Voice]:
        voices: list[Voice] = []
        params = {"page_size": str(VOICES_PAGE_SIZE)}
        for _ in range(VOICES_MAX_PAGES):
            page = await self._listed(api_key, "/v2/voices", params)
            voices += [
                Voice(
                    found["voice_id"],
                    found.get("name") or found["voice_id"],
                    found.get("preview_url"),
                )
                for found in page["voices"]
            ]
            if not page.get("has_more") or not page.get("next_page_token"):
                break
            params = {**params, "next_page_token": page["next_page_token"]}
        return voices

    async def start_call(self, api_key: str, remote_agent_id: str) -> CallJoin:
        answer = await self._listed(
            api_key, "/v1/convai/conversation/token", {"agent_id": remote_agent_id}
        )
        return CallJoin(str(answer["token"]))

    async def _listed(self, api_key: str, path: str, params: dict[str, str]) -> Any:
        """A GET where a 404 is a failure like any other (a gone remote agent can't be
        called)."""
        try:
            return await self._call(api_key, "GET", path, params=params)
        except _GoneError:
            raise VoiceLayerError(f"ElevenLabs has no {path}") from None
