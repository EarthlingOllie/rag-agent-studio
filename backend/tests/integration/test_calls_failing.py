"""API seam: the Calls failing alert (spec 20, ticket 20-09).

When the voice layer can't start a Call (the remote agent is gone, the key was revoked, the
provider is unreachable), the Visitor gets the Unavailable text and the chat, and the Agent's
Calls failing alert is raised: on the Agents list and on Embed & limits. Saving the Call
settings sets the remote agent up again and clears it, as does the next Call that starts.
Messaging is unaffected throughout.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.voice.fake import FakeVoiceLayer
from tests.agents import start_conversation
from tests.conftest import ClientFactory, SignedUpMember
from tests.integration.test_call_settings import change
from tests.integration.test_calls import calling_agent, start_call, started
from tests.integration.test_embed import conversation_token, send, settings_path
from tests.integration.test_playground_calls import start_call as start_playground_call

UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


@pytest.fixture
def voice_layer(app: FastAPI) -> FakeVoiceLayer:
    layer: FakeVoiceLayer = app.state.voice_layer
    return layer


async def calls_failing(owner: SignedUpMember, agent: dict[str, Any]) -> tuple[bool, bool]:
    """The alert as the Agents list shows it, and as Embed & limits shows it."""
    listed = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}/agents"
    )
    assert listed.status_code == 200, listed.text
    [row] = [a for a in listed.json() if a["id"] == agent["id"]]
    settings = await owner.client.get(settings_path(owner, agent["project_id"], agent["id"]))
    assert settings.status_code == 200, settings.text
    return row["calls_failing"], settings.json()["calls_failing"]


async def save_call_settings(owner: SignedUpMember, agent: dict[str, Any]) -> httpx.Response:
    """The Call settings saved as the Studio's card saves them, unchanged."""
    settings = (
        await owner.client.get(settings_path(owner, agent["project_id"], agent["id"]))
    ).json()
    return await change(
        owner,
        agent,
        calls_enabled=settings["calls_enabled"],
        call_credential_id=settings["call_credential_id"],
        call_voice_id=settings["call_voice_id"],
        spoken_greeting=settings["spoken_greeting"],
    )


async def test_a_call_the_voice_layer_cant_start_raises_the_alert_and_messaging_still_works(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    assert await calls_failing(owner, agent) == (False, False)
    voice_layer.failing = True

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == (
        503,
        {"detail": UNAVAILABLE, "reason": "voice_unavailable"},
    )
    assert await calls_failing(owner, agent) == (True, True)
    message = await send(visitor, agent["public_id"], token, "How much leave do I get?")
    assert message.status_code == 200, message.text
    assert "event: done" in message.text


async def test_the_next_call_that_starts_clears_the_alert(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    voice_layer.failing = True
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503
    # A second failure keeps the alert raised.
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503
    assert await calls_failing(owner, agent) == (True, True)
    voice_layer.failing = False

    await started(visitor, agent["public_id"], token)

    assert await calls_failing(owner, agent) == (False, False)


async def test_a_gone_remote_agent_raises_the_alert_and_saving_the_call_settings_sets_it_up_again(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    voice_layer.remote_agents.clear()
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503
    assert await calls_failing(owner, agent) == (True, True)

    saved = await save_call_settings(owner, agent)

    assert saved.status_code == 200, saved.text
    assert saved.json()["calls_failing"] is False
    assert len(voice_layer.remote_agents) == 1
    assert await calls_failing(owner, agent) == (False, False)
    await started(visitor, agent["public_id"], token)


async def test_saving_the_call_settings_while_the_voice_layer_still_fails_keeps_the_alert(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    voice_layer.failing = True
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503

    saved = await save_call_settings(owner, agent)

    assert saved.status_code == 502, saved.text
    assert await calls_failing(owner, agent) == (True, True)


async def test_saving_other_operational_settings_leaves_the_remote_agent_and_the_alert(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    voice_layer.failing = True
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503

    saved = await change(owner, agent, daily_token_budget=5000)

    assert saved.status_code == 200, saved.text
    assert saved.json()["calls_failing"] is True


async def test_turning_calling_off_clears_the_alert(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    voice_layer.remote_agents.clear()
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503

    saved = await change(owner, agent, calls_enabled=False)

    assert saved.status_code == 200, saved.text
    assert await calls_failing(owner, agent) == (False, False)


async def test_a_playground_call_the_voice_layer_cant_start_raises_the_alert_too(
    app: FastAPI, owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    conversation = await start_conversation(owner, agent["project_id"], agent["id"])
    voice_layer.failing = True

    assert (await start_playground_call(owner, agent, conversation["id"])).status_code == 502
    assert await calls_failing(owner, agent) == (True, True)
    voice_layer.failing = False

    started_here = await start_playground_call(owner, agent, conversation["id"])

    assert started_here.status_code == 201, started_here.text
    assert await calls_failing(owner, agent) == (False, False)
