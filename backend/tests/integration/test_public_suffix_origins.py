"""API seam: an Allowed Origin's subdomain wildcard must name a site, not a public suffix
(WID-F4). ``https://*.co.uk`` would let every site under ``.co.uk`` frame the widget and talk to
it, so it is refused when saved and ignored when an older save still holds it."""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.agents.models import Agent
from tests.conftest import ClientFactory, SignedUpMember
from tests.integration.test_embed import allow, boot, conversations_path, live_agent


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.mark.parametrize(
    "origin",
    ["https://*.co.uk", "https://*.github.io", "https://*.com.au", "http://*.CO.UK/"],
)
async def test_a_wildcard_over_a_public_suffix_is_refused(
    owner: SignedUpMember, origin: str
) -> None:
    agent = await live_agent(owner)

    response = await allow(owner, agent["project_id"], agent["id"], "https://shop.test", origin)

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "allowed_origins", 1]


@pytest.mark.parametrize(
    "origin", ["https://*.example.com", "https://*.example.co.uk", "https://*.me.github.io"]
)
async def test_a_wildcard_over_a_named_site_is_allowed(owner: SignedUpMember, origin: str) -> None:
    agent = await live_agent(owner)

    response = await allow(owner, agent["project_id"], agent["id"], origin)

    assert response.status_code == 200, response.text
    assert response.json()["allowed_origins"] == [origin]


async def store_origins(app: FastAPI, agent: dict[str, Any], *origins: str) -> None:
    """Origins saved before public suffixes were refused: written as they were stored then."""
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(Agent)
            .where(Agent.id == uuid.UUID(agent["id"]))
            .values(allowed_origins=list(origins))
        )
        await session.commit()


async def test_a_stored_public_suffix_wildcard_no_longer_lets_its_sites_in(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    await store_origins(app, agent, "https://*.co.uk", "https://*.example.com")
    shell = await visitor.get(f"/widget/a/{agent['public_id']}")
    bootstrap = boot(shell)["bootstrap_token"]

    assert "frame-ancestors https://*.example.com" in shell.headers["content-security-policy"]
    assert "co.uk" not in shell.headers["content-security-policy"]
    refused = await visitor.post(
        conversations_path(agent["public_id"]),
        json={"bootstrap_token": bootstrap},
        headers={"Origin": "https://attacker.co.uk"},
    )
    assert refused.status_code == 403, refused.text
    admitted = await visitor.post(
        conversations_path(agent["public_id"]),
        json={"bootstrap_token": bootstrap},
        headers={"Origin": "https://help.example.com"},
    )
    assert admitted.status_code == 201, admitted.text


async def test_only_stored_public_suffix_wildcards_leave_no_framing_site(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    await store_origins(app, agent, "https://*.github.io")

    shell = await visitor.get(f"/widget/a/{agent['public_id']}")

    assert "frame-ancestors 'none'" in shell.headers["content-security-policy"]
