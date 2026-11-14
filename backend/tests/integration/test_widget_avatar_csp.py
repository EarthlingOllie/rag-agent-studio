"""HTTP seam: the widget shows hosted images only (AGT-F3). An external ``avatar_url`` in a Live
Version would make every Visitor's browser fetch a URL an Editor chose, so the shell no longer
serves it, and its ``Content-Security-Policy`` lets images load only from the widget's own
origin."""

from typing import Any

import httpx
import pytest

from tests import theme_images as images
from tests.agents import create_agent, save_draft
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import create_project
from tests.integration.test_agent_versions import published
from tests.integration.test_branded_widget import upload_avatar
from tests.integration.test_embed import boot, live_agent

EXTERNAL = "https://tracker.example.net/pixel.png"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def directives(shell: httpx.Response) -> dict[str, list[str]]:
    policy: str = shell.headers["content-security-policy"]
    found: dict[str, list[str]] = {}
    for directive in policy.split(";"):
        name, *sources = directive.split()
        found[name] = sources
    return found


async def externally_avatared(owner: SignedUpMember) -> dict[str, Any]:
    """A Live Version whose Experience still holds an external avatar URL."""
    project_id = await create_project(owner)
    agent: dict[str, Any] = await create_agent(owner, project_id)
    draft = {"experience": {"avatar_url": EXTERNAL}}
    assert (await save_draft(owner, project_id, agent["id"], draft)).status_code == 200
    await published(owner, project_id, agent["id"])
    return agent


async def test_the_shell_lets_images_load_only_from_its_own_origin(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner, "https://www.example.com")

    shell = await visitor.get(f"/widget/a/{agent['public_id']}")

    assert shell.status_code == 200, shell.text
    policy = directives(shell)
    assert policy["frame-ancestors"] == ["https://www.example.com"]
    assert policy["img-src"] == ["'self'", "data:", "blob:"]


async def test_an_external_avatar_url_is_not_served_to_visitors(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await externally_avatared(owner)

    shell = await visitor.get(f"/widget/a/{agent['public_id']}")

    assert shell.status_code == 200, shell.text
    assert boot(shell)["avatar_url"] is None
    assert "tracker.example.net" not in shell.text


async def test_an_external_avatar_url_falls_back_to_the_themes_avatar(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await externally_avatared(owner)
    await images.upload(owner, "avatar", images.png(1, 2, 3))

    url = boot(await visitor.get(f"/widget/a/{agent['public_id']}"))["avatar_url"]

    assert url.startswith(f"/widget/a/{agent['public_id']}/avatar?v=")


async def test_an_uploaded_avatar_still_shows(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await externally_avatared(owner)
    own = images.png(9, 9, 9)
    assert (await upload_avatar(owner, agent, own)).status_code == 200

    url = boot(await visitor.get(f"/widget/a/{agent['public_id']}"))["avatar_url"]

    assert url.startswith(f"/widget/a/{agent['public_id']}/avatar?v=")
    assert (await visitor.get(url)).content == own
