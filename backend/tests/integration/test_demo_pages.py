"""API seam: the Demo pages (ticket 10-03). The fictional shop pages (bubble and inline) and the
low-budget page are static, so they ask the API which of the Demo Organisation's Agents to embed
and where the loader lives (``GET /api/demo/agents``). The low-budget page's button spends the
low-budget Agent's Token Budget for today in one click (``POST
/api/demo/agents/{public_id}/exhaust-budget``). Both answer only when ``DEMO_PAGES`` is on, and
only about the seeded Demo Organisation.

Seen as a Visitor would: the shop Agent's widget shell may be framed by the shop origin and no
other, so the disallowed-origin page is refused by the browser.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.mail.outbox import OutboxMailer
from app.seed import content
from app.seed.runner import erase_demo, seed
from tests.agents import parse_sse
from tests.conftest import ClientFactory
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_seed import ASSETS, demo_project, get, signed_in

SHOP_ORIGIN = "http://localhost:5175"
DISALLOWED_ORIGIN = "http://localhost:5176"


pytestmark = pytest.mark.usefixtures("quiet_seed_history")


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    settings_env.setenv("DEMO_PAGES", "true")
    settings_env.setenv("DEMO_SHOP_ORIGIN", SHOP_ORIGIN)
    return settings_env


@pytest.fixture
async def seeded(app: FastAPI) -> FastAPI:
    await erase_demo(app)
    await seed(app, ASSETS)
    return app


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on the demo page: no Studio session."""
    return await new_client()


async def demo_agents(visitor: httpx.AsyncClient) -> dict[str, Any]:
    response = await visitor.get("/api/demo/agents")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_the_demo_pages_learn_which_agents_to_embed_and_where_the_loader_is(
    seeded: FastAPI, visitor: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    found = await demo_agents(visitor)

    owner = await signed_in(new_client, content.OWNER)
    project = await demo_project(owner)
    agents = {a["name"]: a for a in await get(owner, "projects", project["id"], "agents")}
    assert found == {
        "widget_url": "https://studio.example.test",
        "shop": {"public_id": agents["Product FAQ"]["public_id"], "name": "Product FAQ"},
        "budget": {
            "public_id": agents["Low-budget helper"]["public_id"],
            "name": "Low-budget helper",
            "daily_token_budget": 2000,
        },
    }


async def test_the_shop_agent_may_be_framed_by_the_shop_origin_only(
    seeded: FastAPI, visitor: httpx.AsyncClient
) -> None:
    found = await demo_agents(visitor)

    for role in ("shop", "budget"):
        shell = await visitor.get(f"/widget/a/{found[role]['public_id']}")
        assert shell.status_code == 200, shell.text
        policy = shell.headers["content-security-policy"]
        assert policy == f"frame-ancestors {SHOP_ORIGIN}"
        assert DISALLOWED_ORIGIN not in policy


async def test_one_click_spends_the_low_budget_agents_budget_for_today(
    seeded: FastAPI, visitor: httpx.AsyncClient, new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    budget = (await demo_agents(visitor))["budget"]
    token = await conversation_token(visitor, budget["public_id"])

    clicked = await visitor.post(f"/api/demo/agents/{budget['public_id']}/exhaust-budget")

    assert clicked.status_code == 200, clicked.text
    assert clicked.json() == {"tokens_used": 2000, "daily_token_budget": 2000}
    refused = await send(visitor, budget["public_id"], token, "Do you sell honey?")
    assert parse_sse(refused.text) == [
        ("unavailable", {"reason": "budget_exhausted", "message": content.BUDGET_UNAVAILABLE})
    ]
    # The Studio shows the alert and the meter full, and the Owner was emailed once.
    owner = await signed_in(new_client, content.OWNER)
    project = await demo_project(owner)
    agents = {a["name"]: a for a in await get(owner, "projects", project["id"], "agents")}
    low = agents["Low-budget helper"]
    assert low["budget_exhausted"] is True
    used = await get(owner, "projects", project["id"], "agents", low["id"], "token-usage")
    assert (used["tokens_used"], used["exhausted"]) == (2000, True)
    assert [(e.to, e.subject) for e in outbox.sent if "Token Budget" in e.subject] == [
        (content.OWNER.email, "Low-budget helper has used its daily Token Budget")
    ]

    # A second click finds it already spent and changes nothing.
    again = await visitor.post(f"/api/demo/agents/{budget['public_id']}/exhaust-budget")
    assert again.json() == {"tokens_used": 2000, "daily_token_budget": 2000}
    assert len([e for e in outbox.sent if "Token Budget" in e.subject]) == 1


async def test_only_the_low_budget_agent_can_be_exhausted(
    seeded: FastAPI, visitor: httpx.AsyncClient
) -> None:
    shop = (await demo_agents(visitor))["shop"]

    for public_id in (shop["public_id"], "agt_unknown"):
        response = await visitor.post(f"/api/demo/agents/{public_id}/exhaust-budget")
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "Not found."}


async def test_before_the_seed_has_run_the_demo_pages_are_told_to_run_it(
    app: FastAPI, visitor: httpx.AsyncClient
) -> None:
    await erase_demo(app)

    response = await visitor.get("/api/demo/agents")

    assert response.status_code == 404
    assert response.json() == {"detail": "The demo isn't seeded yet. Run `make seed`."}


async def test_outside_a_demo_stack_there_are_no_demo_routes(
    seeded: FastAPI, visitor: httpx.AsyncClient
) -> None:
    budget = (await demo_agents(visitor))["budget"]
    seeded.state.settings.demo_pages = False

    listed = await visitor.get("/api/demo/agents")
    clicked = await visitor.post(f"/api/demo/agents/{budget['public_id']}/exhaust-budget")

    assert [listed.status_code, clicked.status_code] == [404, 404]
    assert listed.json() == clicked.json() == {"detail": "Not found."}
