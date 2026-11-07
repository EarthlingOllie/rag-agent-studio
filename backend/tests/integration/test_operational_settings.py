"""API seam: an Agent's Operational Settings, its Allowed Origins and unavailable text. They are
edited through their own endpoint, apart from the Agent's Drafts and Versions, apply on the next
request without publishing, and every change is an Audit Event with before and after values."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError

from tests.agents import agents_path, answer_with, create_agent, parse_sse
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_embed import (
    allow,
    conversation_token,
    live_agent,
    send,
    settings_path,
)
from tests.integration.test_playground_errors import failing

DEFAULT_UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
CHANGED = "agent.operational_settings_changed"
# The default rate limits (06-05), which these tests leave alone.
LIMITS = {"conversation_messages_per_minute": 10, "ip_messages_per_minute": 30}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def settings(member: SignedUpMember, agent: dict[str, Any]) -> httpx.Response:
    return await member.client.get(settings_path(member, agent["project_id"], agent["id"]))


async def change(member: SignedUpMember, agent: dict[str, Any], **fields: Any) -> httpx.Response:
    return await member.client.patch(
        settings_path(member, agent["project_id"], agent["id"]), json=fields
    )


async def csp(visitor: httpx.AsyncClient, agent: dict[str, Any]) -> str:
    shell = await visitor.get(f"/widget/a/{agent['public_id']}")
    assert shell.status_code == 200, shell.text
    policy: str = shell.headers["content-security-policy"]
    return policy


# Reading and separation from AgentConfig


async def test_a_new_agent_has_no_allowed_origins_and_the_default_unavailable_text(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(owner)

    response = await settings(editor, agent)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "allowed_origins": [],
        "unavailable_text": DEFAULT_UNAVAILABLE,
        **LIMITS,
    }


async def test_operational_settings_are_not_part_of_the_draft_or_a_version(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    before = (await owner.client.get(agents_path(owner, project_id, agent["id"]))).json()

    response = await change(
        owner, agent, allowed_origins=["https://www.example.com"], unavailable_text="Back soon."
    )

    assert response.status_code == 200, response.text
    # The Draft hasn't moved on and holds neither setting.
    after = (await owner.client.get(agents_path(owner, project_id, agent["id"]))).json()
    for field in ("draft", "draft_revision", "draft_updated_at", "live_version"):
        assert after[field] == before[field]
    assert "example.com" not in str(after["draft"])
    assert "Back soon." not in str(after["draft"])
    # Publishing doesn't carry them into the Version, and leaves them as they were.
    version = await published(owner, project_id, agent["id"])
    assert "example.com" not in str(version)
    assert "Back soon." not in str(version)
    assert (await settings(owner, agent)).json() == {
        "allowed_origins": ["https://www.example.com"],
        "unavailable_text": "Back soon.",
        **LIMITS,
    }
    assert await csp(visitor, agent) == "frame-ancestors https://www.example.com"


# Allowed Origins


async def test_an_editor_sets_the_allowed_origins_and_the_next_shell_uses_them(
    owner: SignedUpMember, member_factory: MemberFactory, visitor: httpx.AsyncClient
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(owner)

    response = await allow(
        editor,
        agent["project_id"],
        agent["id"],
        " HTTPS://WWW.Example.com/ ",
        "http://localhost:8080",
        "https://www.example.com",
        "https://shop.example.co.uk:8443",
    )

    expected = [
        "https://www.example.com",
        "http://localhost:8080",
        "https://shop.example.co.uk:8443",
    ]
    assert response.status_code == 200, response.text
    assert response.json() == {
        "allowed_origins": expected,
        "unavailable_text": DEFAULT_UNAVAILABLE,
        **LIMITS,
    }
    assert (await settings(editor, agent)).json()["allowed_origins"] == expected
    # No publish needed: the next shell carries them.
    assert await csp(visitor, agent) == "frame-ancestors " + " ".join(expected)
    assert (await allow(editor, agent["project_id"], agent["id"])).json()["allowed_origins"] == []
    assert await csp(visitor, agent) == "frame-ancestors 'none'"


@pytest.mark.parametrize(
    ("origins", "policy"),
    [
        (["https://*.example.com"], "frame-ancestors https://*.example.com"),
        (
            ["https://*.Example.co.uk:8443", "https://example.co.uk"],
            "frame-ancestors https://*.example.co.uk:8443 https://example.co.uk",
        ),
        (["http://localhost"], "frame-ancestors http://localhost"),
        (["http://localhost:3000"], "frame-ancestors http://localhost:3000"),
        (["http://localhost:*"], "frame-ancestors http://localhost:*"),
        (["https://LOCALHOST:*/"], "frame-ancestors https://localhost:*"),
        (["http://127.0.0.1:5173"], "frame-ancestors http://127.0.0.1:5173"),
        (["http://127.0.0.1:*"], "frame-ancestors http://127.0.0.1:*"),
        (
            ["http://[::1]:5173", "http://[::1]:*"],
            "frame-ancestors http://[::1]:5173 http://[::1]:*",
        ),
    ],
)
async def test_subdomain_wildcards_and_localhost_are_allowed_origins(
    owner: SignedUpMember, visitor: httpx.AsyncClient, origins: list[str], policy: str
) -> None:
    agent = await live_agent(owner)

    response = await change(owner, agent, allowed_origins=origins)

    assert response.status_code == 200, response.text
    assert await csp(visitor, agent) == policy


@pytest.mark.parametrize(
    "origin",
    [
        "www.example.com",
        "ftp://example.com",
        "https://example.com/path",
        "https://example.com; script-src *",
        "https://exa mple.com",
        "https://example.com:0",
        "https://example.com:70000",
        "https://-example.com",
        "javascript:alert(1)",
        "",
        "https://" + "a" * 250 + ".com",
        # Wildcards cover subdomains of a named site, and only as the first label.
        "*",
        "https://*",
        "*.example.com",
        "https://*.com",
        "https://*.co",
        "https://www.*.example.com",
        "https://*example.com",
        "https://**.example.com",
        "https://*.*.example.com",
        "https://example.*",
        "http://*.localhost",
        # Any port only for this machine.
        "https://www.example.com:*",
        "https://*.example.com:*",
        "http://localhost:",
        "http://[::2]:8080",
        "http://[::1",
    ],
)
async def test_a_malformed_allowed_origin_is_refused_and_nothing_is_saved(
    owner: SignedUpMember, origin: str
) -> None:
    agent = await live_agent(owner, "https://www.example.com")

    response = await change(owner, agent, allowed_origins=["https://ok.example.com", origin])

    assert response.status_code == 422, response.text
    (problem,) = response.json()["detail"]
    assert problem["loc"] == ["body", "allowed_origins", 1]
    assert "isn't a site address" in problem["msg"]
    assert (await settings(owner, agent)).json()["allowed_origins"] == ["https://www.example.com"]
    # Only the first save, when the Agent was made live with one origin, is audited.
    assert len(await audit_events(owner, CHANGED)) == 1


async def test_at_most_fifty_allowed_origins(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    origins = [f"https://site{n}.example.com" for n in range(51)]

    response = await change(owner, agent, allowed_origins=origins)

    assert response.status_code == 422, response.text
    assert (await change(owner, agent, allowed_origins=origins[:50])).status_code == 200


# The unavailable text


async def test_the_unavailable_text_is_set_and_visitors_get_it_on_the_next_request(
    owner: SignedUpMember, member_factory: MemberFactory, visitor: httpx.AsyncClient
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(owner)  # The Organisation has no Default Model.
    token = await conversation_token(visitor, agent["public_id"])
    before = await send(visitor, agent["public_id"], token, "Hello?")
    assert before.status_code == 503
    assert before.json()["detail"] == DEFAULT_UNAVAILABLE

    response = await change(
        editor, agent, unavailable_text="  Our helper is having a break. Call us on 0123.  "
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "allowed_origins": [],
        "unavailable_text": "Our helper is having a break. Call us on 0123.",
        **LIMITS,
    }
    # Without publishing, in the same Conversation.
    after = await send(visitor, agent["public_id"], token, "Hello?")
    assert after.status_code == 503
    assert after.json()["detail"] == "Our helper is having a break. Call us on 0123."


async def test_a_provider_failure_shows_visitors_the_unavailable_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(
        app,
        failing(
            ModelHTTPError.for_category(
                ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
            )
        ),
    )
    agent = await create_agent(owner, project_id)
    await published(owner, project_id, agent["id"])
    assert (await change(owner, agent, unavailable_text="Back soon.")).status_code == 200
    token = await conversation_token(visitor, agent["public_id"])

    response = await send(visitor, agent["public_id"], token, "Hello?")

    assert parse_sse(response.text) == [("error", {"code": "invalid_key", "message": "Back soon."})]


@pytest.mark.parametrize("cleared", [None, "", "   "])
async def test_clearing_the_unavailable_text_restores_the_default(
    owner: SignedUpMember, cleared: str | None
) -> None:
    agent = await live_agent(owner)
    assert (await change(owner, agent, unavailable_text="Back soon.")).status_code == 200

    response = await change(owner, agent, unavailable_text=cleared)

    assert response.status_code == 200, response.text
    assert response.json()["unavailable_text"] == DEFAULT_UNAVAILABLE


async def test_the_unavailable_text_is_at_most_500_characters(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)

    too_long = await change(owner, agent, unavailable_text="x" * 501)

    assert too_long.status_code == 422, too_long.text
    assert too_long.json()["detail"][0]["loc"] == ["body", "unavailable_text"]
    assert (await change(owner, agent, unavailable_text="x" * 500)).status_code == 200


async def test_a_change_to_one_setting_leaves_the_other_as_it_was(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    await change(owner, agent, allowed_origins=["https://a.example.com"], unavailable_text="A.")

    await change(owner, agent, unavailable_text="B.")
    await change(owner, agent, allowed_origins=["https://b.example.com"])
    unchanged = await change(owner, agent)

    assert unchanged.status_code == 200
    assert unchanged.json() == {
        "allowed_origins": ["https://b.example.com"],
        "unavailable_text": "B.",
        **LIMITS,
    }


# Auditing


async def test_each_change_is_an_audit_event_with_the_before_and_after_values(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(owner)

    await change(editor, agent, allowed_origins=["https://www.example.com"])
    await change(
        owner,
        agent,
        allowed_origins=["https://www.example.com", "https://*.example.org"],
        unavailable_text="Back soon.",
    )
    await change(editor, agent, unavailable_text=None)

    events = await audit_events(owner, CHANGED)
    # Newest first.
    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            {"type": "agent", "id": agent["id"]},
            {"unavailable_text": "Back soon."},
            {"unavailable_text": DEFAULT_UNAVAILABLE},
        ),
        (
            owner.member_id,
            {"type": "agent", "id": agent["id"]},
            {
                "allowed_origins": ["https://www.example.com"],
                "unavailable_text": DEFAULT_UNAVAILABLE,
            },
            {
                "allowed_origins": ["https://www.example.com", "https://*.example.org"],
                "unavailable_text": "Back soon.",
            },
        ),
        (
            editor.member_id,
            {"type": "agent", "id": agent["id"]},
            {"allowed_origins": []},
            {"allowed_origins": ["https://www.example.com"]},
        ),
    ]


async def test_a_save_that_changes_nothing_is_not_audited(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)
    await change(owner, agent, allowed_origins=["https://www.example.com"], unavailable_text="A.")

    again = await change(
        owner, agent, allowed_origins=["https://WWW.example.com/"], unavailable_text=" A. "
    )

    assert again.status_code == 200
    assert len(await audit_events(owner, CHANGED)) == 1


async def test_a_refused_change_is_not_audited(owner: SignedUpMember) -> None:
    agent = await live_agent(owner)

    response = await change(
        owner, agent, allowed_origins=["https://*"], unavailable_text="Never saved."
    )

    assert response.status_code == 422
    assert await audit_events(owner, CHANGED) == []
    assert (await settings(owner, agent)).json()["unavailable_text"] == DEFAULT_UNAVAILABLE


# Scope


async def test_operational_settings_are_not_found_outside_their_project(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    agent = await live_agent(owner)
    other_project = await create_project(owner)
    stranger = await tenant_factory()

    for path in (
        settings_path(owner, other_project, agent["id"]),
        settings_path(owner, agent["project_id"], "00000000-0000-0000-0000-000000000000"),
    ):
        assert (await owner.client.get(path)).status_code == 404
        assert (await owner.client.patch(path, json={"allowed_origins": []})).status_code == 404
    elsewhere = f"/api/organisations/{stranger.organisation_id}/projects/{agent['project_id']}"
    response = await owner.client.get(f"{elsewhere}/agents/{agent['id']}/operational-settings")
    assert response.status_code == 404
