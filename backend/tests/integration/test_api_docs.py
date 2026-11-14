"""API seam: the interactive API docs and the raw OpenAPI document (AUTH-F3). They map every
endpoint, so they are served only in the ``local`` and ``test`` environments; elsewhere the
paths are Not Found. Generating the TypeScript client renders the document in-process
(``app.openapi``) and so works whatever the environment."""

import httpx
import pytest
from fastapi import FastAPI

from app.openapi import render_openapi

DOC_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


def _use_environment(app: FastAPI, environment: str) -> None:
    # Settings are read per request, as the CSRF middleware does.
    app.state.settings = app.state.settings.model_copy(update={"environment": environment})


@pytest.mark.parametrize("path", DOC_PATHS)
@pytest.mark.parametrize("environment", ["production", "demo"])
async def test_the_docs_are_not_served_outside_local_and_test(
    app: FastAPI, client: httpx.AsyncClient, environment: str, path: str
) -> None:
    _use_environment(app, environment)

    response = await client.get(path)

    assert response.status_code == 404
    assert "openapi" not in response.text.lower()


@pytest.mark.parametrize("path", DOC_PATHS)
@pytest.mark.parametrize("environment", ["local", "test"])
async def test_the_docs_are_served_in_local_and_test(
    app: FastAPI, client: httpx.AsyncClient, environment: str, path: str
) -> None:
    _use_environment(app, environment)

    response = await client.get(path)

    assert response.status_code == 200


async def test_the_docs_pages_load_the_openapi_document(client: httpx.AsyncClient) -> None:
    for path in ("/docs", "/redoc"):
        assert "/openapi.json" in (await client.get(path)).text
    document = (await client.get("/openapi.json")).json()
    assert document["info"]["title"] == "RAG Agent Studio API"
    assert "/api/auth/sign-in" in document["paths"]


async def test_the_docs_routes_are_not_in_the_document(client: httpx.AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]

    assert not set(paths) & {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


def test_the_client_document_renders_without_settings() -> None:
    assert '"/api/auth/sign-in"' in render_openapi()
