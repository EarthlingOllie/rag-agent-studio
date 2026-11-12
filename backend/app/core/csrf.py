"""Cross-site request forgery defence (AUTH-R2-F1).

The Studio session cookie is SameSite=Lax, which a page on a sibling subdomain (same-site) still
gets sent with, and a bodyless POST needs no CORS preflight. So every state-changing request to
``/api/`` must come from the Studio's own pages:

- ``Sec-Fetch-Site``, which every current browser sends and a page cannot forge, must be
  ``same-origin`` when it is present;
- ``Origin``, when present, must be the Studio's (``STUDIO_URL``).

A request with neither header did not come from a browser page, so it can't carry a Visitor's
or Member's cookie on someone else's behalf (scripts and the tests send neither).

The widget's routes are exempt: they are cross-origin by design and authenticated by tokens
the page holds, not by a cookie. So are the demo pages' routes, which no session reaches.
"""

import json

from pydantic import HttpUrl
from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
EXEMPT_PREFIXES = ("/api/widget/", "/api/demo/")
REFUSED = json.dumps({"detail": "Cross-site request refused."}).encode()

_DEFAULT_PORTS = {"http": 80, "https": 443}


def origin_of(url: HttpUrl) -> str:
    """The origin a browser sends in ``Origin`` for pages served from ``url``."""
    origin = f"{url.scheme}://{url.host}"
    if url.port != _DEFAULT_PORTS.get(url.scheme):
        origin += f":{url.port}"
    return origin


def _checked(scope: Scope) -> bool:
    path: str = scope["path"]
    return (
        scope["method"] not in SAFE_METHODS
        and path.startswith("/api/")
        and not path.startswith(EXEMPT_PREFIXES)
    )


def _from_the_studio(headers: dict[bytes, bytes], studio_origin: str) -> bool:
    site = headers.get(b"sec-fetch-site")
    if site is not None and site != b"same-origin":
        return False
    origin = headers.get(b"origin")
    return origin is None or origin.decode("latin-1") == studio_origin


class CsrfMiddleware:
    """Refuses a state-changing ``/api/`` request that another site's page made."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _checked(scope):
            # Read per request: settings are loaded when the app starts.
            studio_origin = origin_of(scope["app"].state.settings.studio_url)
            headers = dict(scope["headers"])
            if not _from_the_studio(headers, studio_origin):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(REFUSED)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": REFUSED})
                return
        await self.app(scope, receive, send)
