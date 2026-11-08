"""How the seed talks to the platform: over HTTP, to the FastAPI app in process, as a person in
the Studio or a Visitor's widget would."""

from typing import Any

import httpx
from fastapi import FastAPI

# HTTPS, so the client's cookie jar sends the Secure session cookie back.
BASE_URL = "https://seed.internal"


class SeedError(Exception):
    """The seed can't go on; the message says why and what to do."""


def new_client(app: FastAPI) -> httpx.AsyncClient:
    """A client with its own cookie jar: another browser."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)


class SeedApi:
    """A client, signed in or not, raising ``SeedError`` on any answer but the expected one."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.organisation = ""

    def path(self, *parts: str) -> str:
        return "/".join(["/api/organisations", self.organisation, *parts])

    async def call(
        self,
        method: str,
        path: str,
        *,
        expect: int = 200,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = await self.client.request(method, path, json=body, headers=headers)
        if response.status_code != expect:
            raise SeedError(f"{method} {path} answered {response.status_code}: {response.text}")
        return response.json()
