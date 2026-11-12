"""The Studio origin the CSRF check compares ``Origin`` with: what a browser sends for pages
served from ``STUDIO_URL``, which names a port only when it is not the scheme's default."""

import pytest
from pydantic import HttpUrl

from app.core.csrf import origin_of


@pytest.mark.parametrize(
    ("studio_url", "origin"),
    [
        ("http://localhost:5173", "http://localhost:5173"),
        ("https://studio.example.test/", "https://studio.example.test"),
        ("https://studio.example.test:443/app", "https://studio.example.test"),
        ("http://studio.example.test:80", "http://studio.example.test"),
        ("https://studio.example.test:8443", "https://studio.example.test:8443"),
    ],
)
def test_the_studio_origin_is_what_a_browser_sends(studio_url: str, origin: str) -> None:
    assert origin_of(HttpUrl(studio_url)) == origin
