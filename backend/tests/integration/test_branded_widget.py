"""API seam: the branded widget. The widget shell inlines the Organisation's Theme, with the
Agent's own Theme override, as CSS custom properties, and the public Experience of the Agent's
Live Version (greeting, starter questions, UI text, citations). The Theme override (colours
and avatar) is Owner-only and is not versioned: it applies to the next shell without
publishing. Visitors use a client with no Studio session."""

import hashlib
import re
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests import theme_images as images
from tests.agents import (
    AUTOMATIC,
    agents_path,
    answer_with,
    create_agent,
    create_automatic_agent,
    parse_sse,
    save_draft,
)
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_embed import boot, cites, conversation_token, live_agent, send
from tests.integration.test_playground import LEAVE
from tests.integration.test_theme import a_theme, theme_path, with_colour
from tests.integration.test_theme_images import stored_objects


@pytest.fixture
async def visitor(new_client: Any) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    client: httpx.AsyncClient = await new_client()
    return client


def theme_css(shell: httpx.Response) -> str:
    found = re.search(r'<style id="widget-theme">(.*?)</style>', shell.text)
    assert found, shell.text
    return found.group(1)


async def shell_of(visitor: httpx.AsyncClient, agent: dict[str, Any]) -> httpx.Response:
    shell = await visitor.get(f"/widget/a/{agent['public_id']}")
    assert shell.status_code == 200, shell.text
    return shell


async def save_theme(owner: SignedUpMember, theme: dict[str, Any]) -> None:
    response = await owner.client.put(theme_path(owner.organisation_id), json=theme)
    assert response.status_code == 200, response.text


# The Theme in the shell

DEFAULT_LIGHT = (
    "#root{color-scheme:light;--theme-primary:#4f46e5;--theme-on-primary:#ffffff;"
    "--theme-surface:#ffffff;--theme-on-surface:#111827;--theme-accent:#0f766e;"
    "--theme-muted:#4b5563;--theme-radius:12px;"
    '--theme-font-family:"Inter", ui-sans-serif, system-ui, sans-serif;}'
)


async def test_the_shell_inlines_the_default_theme_as_css_custom_properties(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)

    shell = await shell_of(visitor, agent)

    assert theme_css(shell) == DEFAULT_LIGHT
    assert boot(shell)["theme"] == {
        "mode": "light",
        "launcher_type": "bubble",
        "launcher_position": "bottom-right",
        "font": "Inter",
    }
    assert (
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600'
        '&amp;display=swap">' in shell.text
    )


async def test_the_shell_uses_the_saved_theme_at_once_in_dark_and_auto_mode(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    theme = with_colour("primary", "#123456", "#abcdef")
    theme.update(radius=4, font="Open Sans", mode="dark", launcher_type="inline")
    await save_theme(owner, theme)

    dark = await shell_of(visitor, agent)

    assert theme_css(dark) == (
        "#root{color-scheme:dark;--theme-primary:#abcdef;--theme-on-primary:#111827;"
        "--theme-surface:#111827;--theme-on-surface:#f9fafb;--theme-accent:#2dd4bf;"
        "--theme-muted:#9ca3af;--theme-radius:4px;"
        '--theme-font-family:"Open Sans", ui-sans-serif, system-ui, sans-serif;}'
    )
    assert boot(dark)["theme"]["launcher_type"] == "inline"
    assert "family=Open+Sans:wght@400;600" in dark.text

    await save_theme(owner, a_theme(mode="auto", launcher_position="bottom-left"))
    auto = await shell_of(visitor, agent)

    assert theme_css(auto) == (
        DEFAULT_LIGHT + "@media (prefers-color-scheme: dark){"
        "#root{color-scheme:dark;--theme-primary:#818cf8;--theme-on-primary:#111827;"
        "--theme-surface:#111827;--theme-on-surface:#f9fafb;--theme-accent:#2dd4bf;"
        "--theme-muted:#9ca3af;--theme-radius:12px;"
        '--theme-font-family:"Inter", ui-sans-serif, system-ui, sans-serif;}}'
    )
    assert boot(auto)["theme"]["mode"] == "auto"
    assert boot(auto)["theme"]["launcher_position"] == "bottom-left"


# The Live Version's Experience in the shell

EXPERIENCE = {
    "display_name": "Hana from HR",
    "greeting": "Hi! Ask me about leave, pay or benefits.",
    "starter_questions": ["How much leave do I get?", "When is payday?"],
    "ui_text": {
        "send_button": "Ask",
        "rate_conversation": "How did Hana do?",
        "unavailable_message": "Hana is on a break. Try again soon.",
        "searching_status": "Hana is looking that up…",
    },
    "rating_prompt_after": 5,
}


async def test_greeting_starter_questions_ui_text_and_citations_come_from_the_live_version(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = {"experience": EXPERIENCE, "retrieval": {"citations": False}}
    assert (await save_draft(owner, project_id, agent["id"], draft)).status_code == 200
    await published(owner, project_id, agent["id"])
    # A later Draft doesn't reach Visitors until it is published.
    later = {
        "experience": {**EXPERIENCE, "greeting": "Draft greeting", "starter_questions": []},
        "retrieval": {"citations": True},
    }
    assert (await save_draft(owner, project_id, agent["id"], later)).status_code == 200

    data = boot(await shell_of(visitor, agent))

    assert data["name"] == "Hana from HR"
    assert data["greeting"] == "Hi! Ask me about leave, pay or benefits."
    assert data["starter_questions"] == ["How much leave do I get?", "When is payday?"]
    assert data["ui_text"] == EXPERIENCE["ui_text"]
    assert data["rating_prompt_after"] == 5
    assert data["citations"] is False

    await published(owner, project_id, agent["id"])
    data = boot(await shell_of(visitor, agent))

    assert data["greeting"] == "Draft greeting"
    assert data["starter_questions"] == []
    assert data["citations"] is True


async def test_an_agent_with_the_default_experience_shows_its_name_and_built_in_text(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)

    data = boot(await shell_of(visitor, agent))

    assert data["name"] == agent["name"]
    assert data["greeting"] == ""
    assert data["starter_questions"] == []
    assert data["ui_text"] == {
        "send_button": None,
        "rate_conversation": None,
        "unavailable_message": None,
        "searching_status": None,
    }
    assert data["rating_prompt_after"] == 3
    assert data["citations"] is True
    assert data["logo_url"] is None
    assert data["avatar_url"] is None


# The per-Agent Theme override


def override_path(member: SignedUpMember, agent: dict[str, Any], *rest: str) -> str:
    return agents_path(member, agent["project_id"], agent["id"], "theme-override", *rest)


async def set_override(
    member: SignedUpMember, agent: dict[str, Any], colours: dict[str, Any]
) -> httpx.Response:
    return await member.client.put(override_path(member, agent), json={"colours": colours})


PRIMARY = {"primary": {"light": "#AA0000", "dark": "#ff8888"}}


async def test_an_owner_overrides_an_agents_colours_and_the_next_shell_uses_them(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    other = await live_agent(owner)
    before = await owner.client.get(override_path(owner, agent))
    assert before.status_code == 200, before.text
    assert before.json() == {"colours": {}, "avatar": None}

    saved = await set_override(owner, agent, PRIMARY)

    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "colours": {"primary": {"light": "#aa0000", "dark": "#ff8888"}},
        "avatar": None,
    }
    assert (await owner.client.get(override_path(owner, agent))).json() == saved.json()
    # No publishing: the next shell has the Agent's primary and the Theme's other colours.
    assert theme_css(await shell_of(visitor, agent)) == DEFAULT_LIGHT.replace(
        "--theme-primary:#4f46e5", "--theme-primary:#aa0000"
    )
    # Other Agents keep the Organisation's Theme.
    assert theme_css(await shell_of(visitor, other)) == DEFAULT_LIGHT

    # The Theme's other colours still follow the Organisation's Theme.
    await save_theme(owner, with_colour("surface", "#fafafa", "#000000"))
    css = theme_css(await shell_of(visitor, agent))
    assert "--theme-primary:#aa0000;" in css
    assert "--theme-surface:#fafafa;" in css

    cleared = await set_override(owner, agent, {})
    assert cleared.json() == {"colours": {}, "avatar": None}
    assert "--theme-primary:#4f46e5;" in theme_css(await shell_of(visitor, agent))


async def test_the_theme_override_is_not_versioned(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    assert (await set_override(owner, agent, PRIMARY)).status_code == 200
    project_id, agent_id = agent["project_id"], agent["id"]

    # Publishing a new Version and reverting to the first leave the override as it is.
    await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "Two."}})
    second = await published(owner, project_id, agent_id)
    assert "theme" not in str(second["config"]).lower()
    reverted = await owner.client.post(agents_path(owner, project_id, agent_id, "revert"))
    assert reverted.status_code == 200, reverted.text

    assert "--theme-primary:#aa0000;" in theme_css(await shell_of(visitor, agent))
    draft = await owner.client.get(agents_path(owner, project_id, agent_id, "draft"))
    assert "#aa0000" not in draft.text


@pytest.mark.parametrize(
    "colours",
    [
        {"primary": {"light": "red", "dark": "#ffffff"}},
        {"primary": {"light": "#ffffff"}},
        {"background": {"light": "#ffffff", "dark": "#000000"}},
        {"primary": {"light": "#ffffff", "dark": "#000000", "hover": "#111111"}},
    ],
)
async def test_an_invalid_colour_override_is_refused(
    colours: dict[str, Any], owner: SignedUpMember
) -> None:
    agent = await live_agent(owner)

    response = await set_override(owner, agent, colours)

    assert response.status_code == 422, response.text
    assert (await owner.client.get(override_path(owner, agent))).json()["colours"] == {}


async def test_only_owners_change_the_theme_override_and_editors_see_it(
    owner: SignedUpMember, member_factory: MemberFactory, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    editor = await member_factory(owner, "editor")
    assert (await set_override(owner, agent, PRIMARY)).status_code == 200

    refused = await set_override(editor, agent, {})

    assert refused.status_code == 403, refused.text
    assert refused.json() == {"detail": "Only Owners can do this"}
    seen = await editor.client.get(override_path(editor, agent))
    assert seen.status_code == 200
    assert seen.json()["colours"] == {"primary": {"light": "#aa0000", "dark": "#ff8888"}}
    started = await editor.client.post(
        override_path(editor, agent, "avatar", "uploads"),
        json={"filename": "a.png", "size_bytes": 10},
    )
    assert started.status_code == 403
    assert (await editor.client.delete(override_path(editor, agent, "avatar"))).status_code == 403
    assert "--theme-primary:#aa0000;" in theme_css(await shell_of(visitor, agent))


async def test_theme_override_changes_are_audit_events(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    await set_override(owner, agent, PRIMARY)
    # Saving the same override again changes nothing and records nothing.
    await set_override(owner, agent, PRIMARY)
    await set_override(owner, agent, {})

    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "agent.theme_override_updated"},
    )

    assert response.status_code == 200, response.text
    events = response.json()["items"]
    assert [(event["before"], event["after"]) for event in events] == [
        ({"colours": {"primary": {"light": "#aa0000", "dark": "#ff8888"}}}, {"colours": {}}),
        ({"colours": {}}, {"colours": {"primary": {"light": "#aa0000", "dark": "#ff8888"}}}),
    ]
    assert {event["target"]["type"] for event in events} == {"agent"}
    assert {event["target"]["id"] for event in events} == {agent["id"]}


async def test_the_theme_override_is_not_found_outside_its_project(
    owner: SignedUpMember, tenant_factory: Any
) -> None:
    agent = await live_agent(owner)
    stranger = await tenant_factory()
    elsewhere = await create_project(owner)

    assert (await stranger.client.get(override_path(owner, agent))).status_code == 404
    moved = {**agent, "project_id": elsewhere}
    assert (await owner.client.get(override_path(owner, moved))).status_code == 404
    assert (await set_override(owner, moved, PRIMARY)).status_code == 404


# Avatars and the logo


async def upload_avatar(
    member: SignedUpMember, agent: dict[str, Any], data: bytes, filename: str = "hana.png"
) -> httpx.Response:
    started = await member.client.post(
        override_path(member, agent, "avatar", "uploads"),
        json={"filename": filename, "size_bytes": len(data)},
    )
    assert started.status_code == 201, started.text
    ticket = started.json()
    await images.put_file(member, ticket, data)
    return await member.client.put(
        override_path(member, agent, "avatar"), json={"upload_id": ticket["upload_id"]}
    )


async def test_an_owner_uploads_an_agent_avatar_and_visitors_see_it(
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(owner)
    data = images.png(200, 10, 10)
    digest = hashlib.sha256(data).hexdigest()[:16]

    confirmed = await upload_avatar(owner, agent, data)

    assert confirmed.status_code == 200, confirmed.text
    avatar = confirmed.json()["avatar"]
    assert avatar == {
        "url": override_path(owner, agent, "avatar") + f"?v={digest}",
        "content_type": "image/png",
        "size_bytes": len(data),
        "uploaded_at": clock.now().isoformat().replace("+00:00", "Z"),
    }
    editor = await member_factory(owner, "editor")
    assert (await editor.client.get(override_path(editor, agent))).json()["avatar"] == avatar
    fetched = await editor.client.get(avatar["url"])
    assert fetched.status_code == 200
    assert fetched.content == data

    data_url = boot(await shell_of(visitor, agent))["avatar_url"]
    assert data_url == f"/widget/a/{agent['public_id']}/avatar?v={digest}"
    image = await visitor.get(data_url)
    assert image.status_code == 200
    assert image.content == data
    assert image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert image.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_the_agents_avatar_wins_over_the_live_versions_and_the_themes(
    owner: SignedUpMember, visitor: httpx.AsyncClient, app: FastAPI
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    hosted = "https://cdn.example.com/hana.png"
    draft = {"experience": {"avatar_url": hosted}}
    assert (await save_draft(owner, project_id, agent["id"], draft)).status_code == 200
    await published(owner, project_id, agent["id"])
    plain = await live_agent(owner)
    theme_avatar = images.png(1, 2, 3)
    theme_digest = hashlib.sha256(theme_avatar).hexdigest()[:16]

    # Without an image of its own the Live Version's avatar shows; else the Theme's, if any.
    assert boot(await shell_of(visitor, agent))["avatar_url"] == hosted
    await images.upload(owner, "avatar", theme_avatar)
    assert boot(await shell_of(visitor, agent))["avatar_url"] == hosted
    plain_url = boot(await shell_of(visitor, plain))["avatar_url"]
    assert plain_url == f"/widget/a/{plain['public_id']}/avatar?v={theme_digest}"
    assert (await visitor.get(plain_url)).content == theme_avatar

    own = images.png(9, 9, 9)
    assert (await upload_avatar(owner, agent, own)).status_code == 200
    own_url = boot(await shell_of(visitor, agent))["avatar_url"]
    assert own_url.startswith(f"/widget/a/{agent['public_id']}/avatar?v=")
    assert (await visitor.get(own_url)).content == own

    # Replacing the Agent's avatar deletes the old file; removing it falls back again.
    first_key = {k for k in stored_objects(app) if f"/agents/{agent['id']}/" in k}
    newer = images.png(8, 8, 8)
    assert (await upload_avatar(owner, agent, newer)).status_code == 200
    keys = {k for k in stored_objects(app) if f"/agents/{agent['id']}/" in k}
    assert len(keys) == 1
    assert keys != first_key
    removed = await owner.client.delete(override_path(owner, agent, "avatar"))
    assert removed.status_code == 200, removed.text
    assert removed.json()["avatar"] is None
    assert not {k for k in stored_objects(app) if f"/agents/{agent['id']}/" in k}
    assert boot(await shell_of(visitor, agent))["avatar_url"] == hosted
    assert (await owner.client.get(override_path(owner, agent, "avatar"))).status_code == 404
    # Removing it again changes nothing.
    assert (await owner.client.delete(override_path(owner, agent, "avatar"))).status_code == 200


async def test_the_themes_logo_is_in_the_shell(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    logo = images.png(4, 5, 6)
    digest = hashlib.sha256(logo).hexdigest()[:16]
    assert (await visitor.get(f"/widget/a/{agent['public_id']}/logo")).status_code == 404
    assert (await visitor.get(f"/widget/a/{agent['public_id']}/avatar")).status_code == 404

    await images.upload(owner, "logo", logo)

    url = boot(await shell_of(visitor, agent))["logo_url"]
    assert url == f"/widget/a/{agent['public_id']}/logo?v={digest}"
    assert (await visitor.get(url)).content == logo
    assert (await visitor.get("/widget/a/agt_unknown/logo")).status_code == 404
    assert (await visitor.get(f"/widget/a/{agent['public_id']}/banner")).status_code == 404


async def test_avatar_changes_are_audit_events(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    data = images.png()
    await upload_avatar(owner, agent, data)
    await owner.client.delete(override_path(owner, agent, "avatar"))

    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "agent.theme_override_updated"},
    )

    described = {
        "content_type": "image/png",
        "size_bytes": len(data),
        "content_hash": hashlib.sha256(data).hexdigest(),
    }
    assert [(e["before"], e["after"]) for e in response.json()["items"]] == [
        ({"avatar": described}, {"avatar": None}),
        ({"avatar": None}, {"avatar": described}),
    ]


async def test_avatar_uploads_are_checked_like_theme_images(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    path = override_path(owner, agent, "avatar")

    svg = await owner.client.post(f"{path}/uploads", json={"filename": "a.svg", "size_bytes": 10})
    assert svg.status_code == 415
    huge = await owner.client.post(
        f"{path}/uploads", json={"filename": "a.png", "size_bytes": 1024 * 1024 + 1}
    )
    assert huge.status_code == 413
    assert huge.json() == {"detail": "Images can be up to 1 MB."}
    unknown = await owner.client.put(path, json={"upload_id": str(uuid.uuid4())})
    assert unknown.status_code == 409

    started = await owner.client.post(
        f"{path}/uploads", json={"filename": "a.png", "size_bytes": 100}
    )
    ticket = started.json()
    not_yet = await owner.client.put(path, json={"upload_id": ticket["upload_id"]})
    assert not_yet.status_code == 409
    assert not_yet.json()["detail"].startswith("The image hasn't reached storage yet.")
    await images.put_file(owner, ticket, images.JPEG)
    wrong = await owner.client.put(path, json={"upload_id": ticket["upload_id"]})
    assert wrong.status_code == 422
    assert wrong.json() == {"detail": "The file isn't a PNG image. Upload it again."}

    started = await owner.client.post(
        f"{path}/uploads", json={"filename": "a.png", "size_bytes": 100}
    )
    ticket = started.json()
    await images.put_file(owner, ticket, images.png() + bytes(1024 * 1024))
    big = await owner.client.put(path, json={"upload_id": ticket["upload_id"]})
    assert big.status_code == 422
    assert big.json() == {"detail": "Images can be up to 1 MB."}

    # An upload is confirmed only for the Agent it was started for.
    other = await live_agent(owner)
    started = await owner.client.post(
        f"{path}/uploads", json={"filename": "a.png", "size_bytes": 100}
    )
    ticket = started.json()
    await images.put_file(owner, ticket, images.png())
    elsewhere = await owner.client.put(
        override_path(owner, other, "avatar"), json={"upload_id": ticket["upload_id"]}
    )
    assert elsewhere.status_code == 409


async def test_avatar_routes_are_not_found_outside_the_project(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    moved = {**agent, "project_id": await create_project(owner)}

    started = await owner.client.post(
        override_path(owner, moved, "avatar", "uploads"),
        json={"filename": "a.png", "size_bytes": 10},
    )
    assert started.status_code == 404
    confirm = await owner.client.put(
        override_path(owner, moved, "avatar"), json={"upload_id": str(uuid.uuid4())}
    )
    assert confirm.status_code == 404
    assert (await owner.client.delete(override_path(owner, moved, "avatar"))).status_code == 404
    assert (await owner.client.get(override_path(owner, moved, "avatar"))).status_code == 404


# Citations


async def test_citations_carry_the_passage_and_follow_the_live_versions_setting(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, cites)
    agent = await create_automatic_agent(owner, project_id)
    await published(owner, project_id, agent["id"])
    token = await conversation_token(visitor, agent["public_id"])

    shown = parse_sse((await send(visitor, agent["public_id"], token, "Leave?")).text)

    assert shown[1] == (
        "citation",
        {"label": "C1", "document_name": "leave.txt", "passage": LEAVE},
    )

    # A Live Version that hides citations streams the answer without them.
    off = {"retrieval": {**AUTOMATIC, "citations": False}}
    assert (await save_draft(owner, project_id, agent["id"], off)).status_code == 200
    await published(owner, project_id, agent["id"])

    hidden = parse_sse((await send(visitor, agent["public_id"], token, "Leave?")).text)

    assert [event for event, _ in hidden] == ["token", "done"]
