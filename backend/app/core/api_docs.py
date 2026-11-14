"""Hides the interactive API docs and the OpenAPI document outside local development and the
tests (AUTH-F3): they map every endpoint. Generating the TypeScript client calls
``app.openapi()`` in-process, so it is unaffected."""

import json

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

DOCS_ENVIRONMENTS = frozenset({"local", "test"})
NOT_FOUND = json.dumps({"detail": "Not Found"}).encode()


def _docs_paths(app: FastAPI) -> set[str]:
    paths = (app.openapi_url, app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url)
    return {path for path in paths if path}


class ApiDocsMiddleware:
    """Answers the docs' paths with 404 unless the environment is ``local`` or ``test``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            application: FastAPI = scope["app"]
            # Read per request: settings are loaded when the app starts.
            environment = application.state.settings.environment
            if environment not in DOCS_ENVIRONMENTS and scope["path"] in _docs_paths(application):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(NOT_FOUND)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": NOT_FOUND})
                return
        await self.app(scope, receive, send)
