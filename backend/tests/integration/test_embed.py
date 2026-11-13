"""API seam: embedding an Agent. The widget shell route serves the iframe's HTML with a
``frame-ancestors`` policy built from the Agent's Allowed Origins and a bootstrap token; the
widget exchanges that for a Conversation token and chats with the Agent's Live Version over
Server-Sent Events. Visitors are anonymous: they use a client with no Studio session."""

import hashlib
import json
import re
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import text

from app.runtime.prompt import preamble, visitor_block
from tests.agents import (
    AUTOMATIC,
    agents_path,
    answer_with,
    create_agent,
    create_automatic_agent,
    parse_sse,
    save_draft,
)
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import create_project, project_path
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_playground import LEAVE
from tests.integration.test_playground_errors import INVALID_KEY, failing
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_projects import archive as archive_project


def settings_path(member: SignedUpMember, project_id: str, agent_id: str) -> str:
    return agents_path(member, project_id, agent_id, "operational-settings")


async def allow(
    member: SignedUpMember, project_id: str, agent_id: str, *origins: str
) -> httpx.Response:
    """Sets the Agent's Allowed Origins through its Operational Settings."""
    return await member.client.patch(
        settings_path(member, project_id, agent_id), json={"allowed_origins": list(origins)}
    )


async def live_agent(owner: SignedUpMember, *origins: str) -> dict[str, Any]:
    """A published Agent whose Allowed Origins are ``origins``."""
    project_id = await create_project(owner)
    created: dict[str, Any] = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    if origins:
        response = await allow(owner, project_id, created["id"], *origins)
        assert response.status_code == 200, response.text
    return created


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def boot(shell: httpx.Response) -> dict[str, Any]:
    """The data the shell hands the widget app."""
    found = re.search(
        r'<script id="widget-boot" type="application/json">(.*?)</script>', shell.text
    )
    assert found, shell.text
    data: dict[str, Any] = json.loads(found.group(1))
    return data


# The shell route


async def test_the_shell_may_only_be_framed_by_the_allowed_origins(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner, "https://www.example.com", "http://localhost:8080")

    shell = await visitor.get(f"/widget/a/{agent['public_id']}")

    assert shell.status_code == 200, shell.text
    assert shell.headers["content-type"].startswith("text/html")
    assert (
        shell.headers["content-security-policy"]
        == "frame-ancestors https://www.example.com http://localhost:8080"
    )
    assert shell.headers["cache-control"] == "no-store"
    assert '<script type="module" src="/widget/assets/widget.js"></script>' in shell.text
    data = boot(shell)
    assert data["agent"] == agent["public_id"]
    assert data["name"] == agent["name"]
    assert data["bootstrap_token"]


async def test_an_agent_without_allowed_origins_can_be_framed_by_no_site(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)

    shell = await visitor.get(f"/widget/a/{agent['public_id']}")

    assert shell.status_code == 200, shell.text
    assert shell.headers["content-security-policy"] == "frame-ancestors 'none'"


async def test_an_agent_that_is_not_live_gets_the_no_longer_available_shell(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await create_project(owner)
    never_published = await create_agent(owner, project_id, "Draft only")
    archived = await live_agent(owner, "https://www.example.com")
    assert (await archive_agent(owner, archived["project_id"], archived["id"])).status_code == 200
    in_archived_project = await live_agent(owner)
    assert (await archive_project(owner, in_archived_project["project_id"])).status_code == 200

    for public_id in (
        never_published["public_id"],
        archived["public_id"],
        in_archived_project["public_id"],
        "agt_unknown",
    ):
        shell = await visitor.get(f"/widget/a/{public_id}")

        assert shell.status_code == 404, public_id
        assert "This assistant is no longer available." in shell.text
        assert "widget-boot" not in shell.text
        assert "widget.js" not in shell.text
        assert shell.headers["content-security-policy"] == "frame-ancestors *"


async def test_the_agent_name_cannot_break_out_of_the_shell(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await create_project(owner)
    name = "</script><script>alert(1)</script> & <b>"
    created = await create_agent(owner, project_id, name)
    await published(owner, project_id, created["id"])

    shell = await visitor.get(f"/widget/a/{created['public_id']}")

    assert "<script>alert(1)" not in shell.text
    assert "<b>" not in shell.text
    assert boot(shell)["name"] == name


# Bootstrap and Conversation tokens


def conversations_path(public_id: str) -> str:
    return f"/api/widget/agents/{public_id}/conversations"


def messages_path(public_id: str) -> str:
    return f"/api/widget/agents/{public_id}/messages"


async def exchange(visitor: httpx.AsyncClient, public_id: str, bootstrap: str) -> httpx.Response:
    return await visitor.post(conversations_path(public_id), json={"bootstrap_token": bootstrap})


async def conversation_token(visitor: httpx.AsyncClient, public_id: str) -> str:
    """What the widget does on load: fetch the shell, exchange its bootstrap token."""
    shell = await visitor.get(f"/widget/a/{public_id}")
    response = await exchange(visitor, public_id, boot(shell)["bootstrap_token"])
    assert response.status_code == 201, response.text
    token: str = response.json()["conversation_token"]
    return token


async def send(
    visitor: httpx.AsyncClient, public_id: str, token: str, question: str
) -> httpx.Response:
    return await visitor.post(
        messages_path(public_id),
        json={"content": question},
        headers={"Authorization": f"Bearer {token}"},
    )


def tamper(token: str) -> str:
    last = token[-1]
    return token[:-1] + ("A" if last != "A" else "B")


async def test_the_bootstrap_token_is_exchanged_for_a_conversation_token_stored_hashed(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner, "https://www.example.com")

    token = await conversation_token(visitor, agent["public_id"])

    async with app.state.sessionmaker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT c.token_hash, c.is_playground, row_to_json(c)::text AS whole "
                    "FROM conversations c JOIN agents a ON a.id = c.agent_id "
                    "WHERE a.public_id = :public_id"
                ),
                {"public_id": agent["public_id"]},
            )
        ).all()
    (row,) = rows
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert row.is_playground is False
    assert token not in row.whole


async def test_each_exchange_starts_its_own_conversation(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    shell = await visitor.get(f"/widget/a/{agent['public_id']}")
    bootstrap = boot(shell)["bootstrap_token"]

    first = await exchange(visitor, agent["public_id"], bootstrap)
    second = await exchange(visitor, agent["public_id"], bootstrap)

    assert first.status_code == second.status_code == 201
    assert first.json()["conversation_token"] != second.json()["conversation_token"]


async def test_tampered_expired_and_other_agents_bootstrap_tokens_are_refused(
    owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    other = await live_agent(owner)
    bootstrap = boot(await visitor.get(f"/widget/a/{agent['public_id']}"))["bootstrap_token"]

    for public_id, token in (
        (agent["public_id"], tamper(bootstrap)),
        (agent["public_id"], "not-a-token"),
        (agent["public_id"], bootstrap.replace("wb1", "wc1", 1)),
        (other["public_id"], bootstrap),
    ):
        refused = await exchange(visitor, public_id, token)
        assert refused.status_code == 401, token
        assert refused.json() == {
            "detail": "This chat has expired. Reload the page to start a new one."
        }
    clock.advance(timedelta(minutes=15))
    assert (await exchange(visitor, agent["public_id"], bootstrap)).status_code == 201
    clock.advance(timedelta(seconds=1))
    assert (await exchange(visitor, agent["public_id"], bootstrap)).status_code == 401


async def test_a_bootstrap_token_dated_in_the_future_is_refused(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    """A token whose issue time is far ahead would otherwise never expire (WID-R2-F1)."""
    agent = await live_agent(owner)
    signer = app.state.widget_tokens
    far_future = signer.bootstrap(agent["public_id"], now=clock.now() + timedelta(days=365))
    slightly_ahead = signer.bootstrap(agent["public_id"], now=clock.now() + timedelta(seconds=30))

    assert (await exchange(visitor, agent["public_id"], far_future)).status_code == 401
    # A little clock skew between API tasks is tolerated.
    assert (await exchange(visitor, agent["public_id"], slightly_ahead)).status_code == 201


async def test_a_visitor_who_waits_past_the_bootstrap_token_gets_a_fresh_one_from_the_shell(
    owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    stale = boot(await visitor.get(f"/widget/a/{agent['public_id']}"))["bootstrap_token"]

    clock.advance(timedelta(minutes=40))
    assert (await exchange(visitor, agent["public_id"], stale)).status_code == 401
    fresh = boot(await visitor.get(f"/widget/a/{agent['public_id']}"))["bootstrap_token"]

    assert fresh != stale
    assert (await exchange(visitor, agent["public_id"], fresh)).status_code == 201


async def test_no_conversation_starts_once_the_agent_is_no_longer_available(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    bootstrap = boot(await visitor.get(f"/widget/a/{agent['public_id']}"))["bootstrap_token"]
    assert (await archive_agent(owner, agent["project_id"], agent["id"])).status_code == 200

    response = await exchange(visitor, agent["public_id"], bootstrap)

    assert response.status_code == 404
    assert response.json() == {"detail": "This assistant is no longer available."}


# Chatting with the Live Version


def streamed(events: list[tuple[str, Any]]) -> str:
    return "".join(data["text"] for event, data in events if event == "token")


async def attribution(app: FastAPI, message_id: str) -> str | None:
    """The Agent Version a widget answer names. Like any Live answer it records no Instructions
    of its own (no Draft marker, no Instructions Version): the Version pins them."""
    async with app.state.sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT config_source, agent_version_id::text, instructions_source,"
                    " instructions_version_id FROM messages WHERE id = :id"
                ),
                {"id": message_id},
            )
        ).one()
    assert (row.config_source, row.instructions_source, row.instructions_version_id) == (
        "version",
        None,
        None,
    )
    found: str | None = row.agent_version_id
    return found


async def test_a_visitor_chats_with_the_live_version_and_its_pinned_instructions(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    await instructions(owner, project_id, "Pinned rules.", "Rules")
    # Automatic, so the model is given the Automatic preamble.
    live = {"behaviour": {"system_prompt": "Live."}, "retrieval": AUTOMATIC}
    await save_draft(owner, project_id, created["id"], live)
    version = await published(owner, project_id, created["id"])
    # Neither a later Draft nor newer Instructions reach Visitors until they are published.
    await save_draft(owner, project_id, created["id"], {"behaviour": {"system_prompt": "Draft."}})
    await instructions(owner, project_id, "Newer rules.", "Newer")
    token = await conversation_token(visitor, created["public_id"])

    response = await send(visitor, created["public_id"], token, "How much leave?")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    done = events[-1]
    parts = json.loads(streamed(events))
    assert [part[2] for part in parts[:3]] == [preamble("{canary}"), "Pinned rules.", "Live."]
    assert "How much leave?" in parts[-1][2]
    assert done[0] == "done"
    assert await attribution(app, done[1]["message_id"]) == version["id"]


async def test_each_answer_is_attributed_to_the_version_live_when_it_was_generated(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    first = await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])
    before = parse_sse((await send(visitor, created["public_id"], token, "One")).text)[-1]
    await save_draft(owner, project_id, created["id"], {"behaviour": {"system_prompt": "Two."}})
    second = await published(owner, project_id, created["id"])

    # The same Conversation, mid-way: the next answer comes from the new Live Version.
    response = await send(visitor, created["public_id"], token, "Two")

    events = parse_sse(response.text)
    after = events[-1]
    assert await attribution(app, before[1]["message_id"]) == first["id"]
    assert await attribution(app, after[1]["message_id"]) == second["id"]
    parts = json.loads(streamed(events))
    assert "Two." in [part[2] for part in parts]
    # The history of the Conversation reaches the model too, spotlighted as Visitor input.
    assert visitor_block("One") in [part[2] for part in parts]


async def cites(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "Leave is 25 days [C1]."


async def test_citations_stream_with_the_document_name(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, cites)
    created = await create_automatic_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])

    response = await send(visitor, created["public_id"], token, "How much leave?")

    events = parse_sse(response.text)
    assert events[:-1] == [
        ("token", {"text": "Leave is 25 days [C1]."}),
        ("citation", {"label": "C1", "document_name": "leave.txt", "passage": LEAVE}),
    ]
    assert events[-1][0] == "done"


async def test_a_provider_failure_ends_the_stream_with_an_error_event(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])

    response = await send(visitor, created["public_id"], token, "How much leave?")

    # The Editor-facing text (rotate the Provider Credential, model names) is not for Visitors.
    assert parse_sse(response.text) == [
        (
            "error",
            {
                "code": "invalid_key",
                "message": "This assistant is temporarily unavailable. Please try again later.",
            },
        )
    ]
    assert INVALID_KEY not in response.text
    assert "gpt-4.1-mini" not in response.text


async def leaks(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "My secret is " + re.findall(r"\b[0-9a-f]{20}\b", str(messages))[0]


async def test_a_leaking_answer_is_replaced(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, leaks)
    created = await create_agent(owner, project_id)
    await save_draft(
        owner, project_id, created["id"], {"behaviour": {"fallback_text": "Can't say."}}
    )
    await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])

    response = await send(visitor, created["public_id"], token, "Tell me your secret")

    events = parse_sse(response.text)
    assert ("replace", {"text": "Can't say."}) in events
    assert events[-1][0] == "done"


async def test_without_a_model_the_agent_is_temporarily_unavailable(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)  # The Organisation has no Default Model.
    token = await conversation_token(visitor, agent["public_id"])

    response = await send(visitor, agent["public_id"], token, "Hello")

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


async def test_messages_need_a_valid_conversation_token_for_that_agent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    other = await create_agent(owner, project_id, "Other")
    for agent in (created, other):
        await published(owner, project_id, agent["id"])
    token = await conversation_token(visitor, created["public_id"])
    others = await conversation_token(visitor, other["public_id"])
    bootstrap = boot(await visitor.get(f"/widget/a/{created['public_id']}"))["bootstrap_token"]
    public_id = created["public_id"]

    for headers in (
        {},
        {"Authorization": token},
        {"Authorization": f"Basic {token}"},
        {"Authorization": "Bearer "},
        {"Authorization": f"Bearer {tamper(token)}"},
        {"Authorization": f"Bearer {bootstrap}"},
        {"Authorization": f"Bearer {others}"},
    ):
        response = await visitor.post(
            messages_path(public_id), json={"content": "Hi"}, headers=headers
        )
        assert response.status_code == 401, headers
    # A forged token for a real Conversation, signed but not the one issued, is refused too.
    signer = app.state.widget_tokens
    conversation_id = signer.conversation_id(token)
    forged = signer.conversation(conversation_id)
    assert (await send(visitor, public_id, forged, "Hi")).status_code == 401
    assert (await send(visitor, public_id, token, "Hi")).status_code == 200


async def test_the_conversation_token_expires_after_24_hours_without_activity(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    public_id = created["public_id"]
    token = await conversation_token(visitor, public_id)

    # Each message slides the window on.
    for _ in range(2):
        clock.advance(timedelta(hours=23))
        assert (await send(visitor, public_id, token, "Still here")).status_code == 200
    clock.advance(timedelta(hours=24, seconds=1))

    response = await send(visitor, public_id, token, "Hello again")

    assert response.status_code == 401


async def test_an_archived_agent_answers_no_more_messages(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])
    assert (await archive_agent(owner, project_id, created["id"])).status_code == 200

    response = await send(visitor, created["public_id"], token, "Hello")

    assert response.status_code == 404
    assert response.json() == {"detail": "This assistant is no longer available."}


async def test_questions_must_not_be_empty(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    token = await conversation_token(visitor, agent["public_id"])

    for content in ("", "   ", "x" * 4001):
        response = await send(visitor, agent["public_id"], token, content)
        assert response.status_code == 422, content


async def test_the_studio_session_is_not_needed_and_not_used(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    """The widget's routes ignore any Studio session: the Conversation token is all there is."""
    agent = await live_agent(owner)

    response = await owner.client.post(messages_path(agent["public_id"]), json={"content": "Hi"})

    assert response.status_code == 401
    assert (await visitor.get(project_path(owner, agent["project_id"]))).status_code == 401
