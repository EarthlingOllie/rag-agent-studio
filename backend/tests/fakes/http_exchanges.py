"""Recorded HTTP exchanges, replayed and recorded through ``httpx`` transports.

A recording is a JSON list of exchanges in the order they happened: each the request (method,
URL, query parameters, JSON body) and the response (status, JSON body). ``Replay`` answers each
request with the next recorded response, after checking the request is the one recorded, so an
adapter tested against it sends exactly what the provider was sent. ``Recorder`` wraps a real
transport and writes a recording (the live suite uses it to refresh the fixtures). Credentials
are never recorded: they travel in headers, which are left out.
"""

import json
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> list[dict[str, Any]]:
    exchanges: list[dict[str, Any]] = json.loads((FIXTURES / name).read_text())
    return exchanges


def _request(request: httpx.Request) -> dict[str, Any]:
    recorded: dict[str, Any] = {
        "method": request.method,
        "url": str(request.url.copy_with(query=None)),
    }
    if request.url.params:
        recorded["params"] = dict(request.url.params)
    if request.content:
        recorded["json"] = json.loads(request.content)
    return recorded


def _response(response: httpx.Response) -> dict[str, Any]:
    recorded: dict[str, Any] = {"status": response.status_code}
    if response.content:
        recorded["json"] = response.json()
    return recorded


class Replay(httpx.AsyncBaseTransport):
    """Answers with a recording's responses, in order. ``seen`` holds each request sent;
    ``done`` is whether every recorded exchange was used."""

    def __init__(self, exchanges: list[dict[str, Any]]) -> None:
        self._exchanges = list(exchanges)
        self.seen: list[httpx.Request] = []

    @property
    def done(self) -> bool:
        return not self._exchanges

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        assert self._exchanges, f"unexpected request: {request.method} {request.url}"
        exchange = self._exchanges.pop(0)
        assert _request(request) == exchange["request"]
        answer = exchange["response"]
        if "json" in answer:
            return httpx.Response(answer["status"], json=answer["json"])
        return httpx.Response(answer["status"])


class Recorder(httpx.AsyncBaseTransport):
    """Passes requests to ``transport`` and keeps each exchange, for ``save``."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport
        self.exchanges: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._transport.handle_async_request(request)
        await response.aread()
        self.exchanges.append({"request": _request(request), "response": _response(response)})
        return response

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.exchanges, indent=2) + "\n")
