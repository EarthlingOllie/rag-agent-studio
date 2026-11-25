"""API seam: an Agent's Call settings (spec 20). Editors turn calling on in the Operational
Settings with a voice-capable credential, one of its account's voices and a spoken greeting;
saving sets the Agent up in the voice layer, later saves update it, and turning calling off,
changing the credential, or archiving or deleting the Agent removes it.

The voice layer is the scripted fake (``VOICE_LAYER=fake``); tests read the remote agents it
holds from ``app.state.voice_layer``, as other tests read the mail outbox. Everything else is
observed through the API.
"""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl

from app.agents.models import Agent
from app.voice.fake import FakeRemoteAgent, FakeVoiceLayer
from app.voice.remote import call_secret
from tests.agents import agents_path, create_agent
from tests.conftest import STUDIO_URL, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_agent_archive import archive, delete_permanently, restore
from tests.integration.test_elevenlabs_credentials import ELEVENLABS_KEY
from tests.integration.test_embed import settings_path
from tests.integration.test_project_deletion import (
    delete_permanently as delete_project_permanently,
)
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import added, audit_events, credentials_path

CHANGED = "agent.operational_settings_changed"
CALLS_OFF = {
    "calls_enabled": False,
    "call_credential_id": None,
    "call_voice_id": None,
    "spoken_greeting": "",
}
ANOTHER_ELEVENLABS_KEY = "sk_test_only_4444444444444444444444444444444444-2nd"


@pytest.fixture
def voice_layer(app: FastAPI) -> FakeVoiceLayer:
    layer: FakeVoiceLayer = app.state.voice_layer
    return layer


async def add_elevenlabs_credential(
    owner: SignedUpMember, api_key: str = ELEVENLABS_KEY
) -> dict[str, Any]:
    return await added(owner, provider="elevenlabs", api_key=api_key)


async def an_agent(member: SignedUpMember) -> dict[str, Any]:
    project_id = await create_project(member)
    agent: dict[str, Any] = await create_agent(member, project_id, name="Front desk")
    return agent


async def change(member: SignedUpMember, agent: dict[str, Any], **fields: Any) -> httpx.Response:
    return await member.client.patch(
        settings_path(member, agent["project_id"], agent["id"]), json=fields
    )


async def call_settings(member: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    response = await member.client.get(settings_path(member, agent["project_id"], agent["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    return {key: body[key] for key in CALLS_OFF}


async def calling_on(
    member: SignedUpMember, agent: dict[str, Any], credential_id: str, **fields: Any
) -> dict[str, Any]:
    response = await change(
        member,
        agent,
        calls_enabled=True,
        call_credential_id=credential_id,
        call_voice_id="fake-voice-ada",
        spoken_greeting="Hello, you're through to the front desk.",
        **fields,
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def refusal(response: httpx.Response) -> tuple[list[Any], str, str]:
    assert response.status_code == 422, response.text
    (problem,) = response.json()["detail"]
    return problem["loc"], problem["type"], problem["msg"]


async def stored_secret(app: FastAPI, agent: dict[str, Any]) -> tuple[bytes | None, str | None]:
    async with app.state.sessionmaker() as session:
        row = await session.get_one(Agent, uuid.UUID(agent["id"]))
        return row.call_secret_sealed, call_secret(app.state.envelope, row)


def only(voice_layer: FakeVoiceLayer) -> tuple[str, FakeRemoteAgent]:
    ((remote_agent_id, remote_agent),) = voice_layer.remote_agents.items()
    return remote_agent_id, remote_agent


# Defaults and turning calling on


async def test_a_new_agent_has_calling_off(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await an_agent(owner)

    assert await call_settings(editor, agent) == CALLS_OFF


async def test_an_editor_turns_calling_on_and_the_agent_is_set_up_in_the_voice_layer(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    voice_layer: FakeVoiceLayer,
) -> None:
    editor = await member_factory(owner, "editor")
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)

    saved = await calling_on(editor, agent, credential["id"])

    assert {key: saved[key] for key in CALLS_OFF} == {
        "calls_enabled": True,
        "call_credential_id": credential["id"],
        "call_voice_id": "fake-voice-ada",
        "spoken_greeting": "Hello, you're through to the front desk.",
    }
    _, remote_agent = only(voice_layer)
    assert remote_agent.api_key == ELEVENLABS_KEY
    spec = remote_agent.spec
    assert spec.voice_id == "fake-voice-ada"
    assert spec.language == "en"
    assert spec.spoken_greeting == "Hello, you're through to the front desk."
    assert spec.llm_url == f"{STUDIO_URL}/api/widget/agents/{agent['public_id']}/llm/v1"
    assert spec.extra_body is True
    # The per-Agent secret is the platform's, stored only sealed.
    sealed, opened = await stored_secret(app, agent)
    assert sealed is not None
    assert spec.llm_secret.encode() not in sealed
    assert opened == spec.llm_secret
    assert len(spec.llm_secret) >= 32
    # It applies at once and is audited with the other Operational Settings.
    assert await call_settings(owner, agent) == {key: saved[key] for key in CALLS_OFF}
    (event,) = await audit_events(owner, CHANGED)
    assert event["actor"]["id"] == editor.member_id
    assert event["before"] == CALLS_OFF
    assert event["after"] == {key: saved[key] for key in CALLS_OFF}


async def test_the_turn_endpoint_is_on_the_platforms_public_base_url(
    app: FastAPI, owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    app.state.settings = app.state.settings.model_copy(
        update={"public_base_url": HttpUrl("https://calls.example.test/")}
    )
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)

    await calling_on(owner, agent, credential["id"])

    _, remote_agent = only(voice_layer)
    assert (
        remote_agent.spec.llm_url
        == f"https://calls.example.test/api/widget/agents/{agent['public_id']}/llm/v1"
    )


async def test_later_saves_update_the_same_remote_agent(
    app: FastAPI, owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    remote_agent_id, first = only(voice_layer)

    response = await change(
        owner, agent, call_voice_id="fake-voice-bryn", spoken_greeting="  Hi there.  "
    )

    assert response.status_code == 200, response.text
    assert response.json()["spoken_greeting"] == "Hi there."
    assert only(voice_layer)[0] == remote_agent_id
    updated = voice_layer.remote_agents[remote_agent_id].spec
    assert (updated.voice_id, updated.spoken_greeting) == ("fake-voice-bryn", "Hi there.")
    assert updated.llm_secret == first.spec.llm_secret
    (event, _) = await audit_events(owner, CHANGED)
    assert event["before"] == {
        "call_voice_id": "fake-voice-ada",
        "spoken_greeting": "Hello, you're through to the front desk.",
    }
    assert event["after"] == {"call_voice_id": "fake-voice-bryn", "spoken_greeting": "Hi there."}


async def test_a_blank_spoken_greeting_says_nothing(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])

    response = await change(owner, agent, spoken_greeting=None)

    assert response.status_code == 200, response.text
    assert response.json()["spoken_greeting"] == ""
    assert only(voice_layer)[1].spec.spoken_greeting == ""


async def test_saving_other_settings_leaves_the_remote_agent_alone(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    before = dict(voice_layer.remote_agents)
    voice_layer.failing = True

    # The voice layer is down, yet the unavailable text can still be changed.
    response = await change(owner, agent, unavailable_text="Back soon.")

    assert response.status_code == 200, response.text
    assert voice_layer.remote_agents == before


# Removing the remote agent


async def test_turning_calling_off_removes_the_remote_agent(
    app: FastAPI, owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])

    response = await change(owner, agent, calls_enabled=False)

    assert response.status_code == 200, response.text
    assert response.json()["calls_enabled"] is False
    # The credential and voice stay chosen for next time.
    assert response.json()["call_credential_id"] == credential["id"]
    assert voice_layer.remote_agents == {}
    assert await stored_secret(app, agent) == (None, None)
    (event, _) = await audit_events(owner, CHANGED)
    assert (event["before"], event["after"]) == ({"calls_enabled": True}, {"calls_enabled": False})


async def test_calling_turns_off_even_while_the_voice_layer_is_down(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    voice_layer.failing = True

    response = await change(owner, agent, calls_enabled=False)

    assert response.status_code == 200, response.text
    assert (await call_settings(owner, agent))["calls_enabled"] is False


async def test_turning_calling_back_on_sets_up_a_new_remote_agent_with_a_new_secret(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    first_id, first = only(voice_layer)
    await change(owner, agent, calls_enabled=False)

    response = await change(owner, agent, calls_enabled=True)

    assert response.status_code == 200, response.text
    second_id, second = only(voice_layer)
    assert second_id != first_id
    assert second.spec.llm_secret != first.spec.llm_secret


async def test_changing_the_credential_moves_the_remote_agent_to_its_account(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    first = await add_elevenlabs_credential(owner)
    second = await added(owner, provider="elevenlabs", api_key=ANOTHER_ELEVENLABS_KEY)
    agent = await an_agent(owner)
    await calling_on(owner, agent, first["id"])
    old_id, old = only(voice_layer)

    response = await change(owner, agent, call_credential_id=second["id"])

    assert response.status_code == 200, response.text
    new_id, new = only(voice_layer)
    assert new_id != old_id
    assert new.api_key == ANOTHER_ELEVENLABS_KEY
    assert new.spec.llm_secret == old.spec.llm_secret


async def test_a_credential_chosen_while_calling_is_off_sets_nothing_up(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)

    response = await change(
        owner, agent, call_credential_id=credential["id"], call_voice_id="fake-voice-cato"
    )

    assert response.status_code == 200, response.text
    assert response.json()["call_voice_id"] == "fake-voice-cato"
    assert voice_layer.remote_agents == {}


async def test_archiving_removes_the_remote_agent_and_saving_after_a_restore_sets_it_up_again(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])

    archived = await archive(owner, agent["project_id"], agent["id"])
    assert archived.status_code == 200, archived.text
    assert voice_layer.remote_agents == {}
    # An archived Agent's Call settings can change, but it gets no remote agent.
    assert (await change(owner, agent, spoken_greeting="Closed.")).status_code == 200
    assert voice_layer.remote_agents == {}

    restored = await restore(owner, agent["project_id"], agent["id"])
    assert restored.status_code == 200, restored.text
    assert voice_layer.remote_agents == {}
    resaved = await change(owner, agent, unavailable_text="Back soon.")

    assert resaved.status_code == 200, resaved.text
    assert only(voice_layer)[1].spec.spoken_greeting == "Closed."


async def test_deleting_an_agent_leaves_no_remote_agent(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    await archive(owner, agent["project_id"], agent["id"])

    response = await delete_permanently(owner, agent["project_id"], agent["id"], "Front desk")

    assert response.status_code == 204, response.text
    assert voice_layer.remote_agents == {}
    # Nothing calls with the credential any more.
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, credential["id"]))
    assert deleted.status_code == 204, deleted.text


async def test_deleting_a_project_leaves_none_of_its_agents_remote_agents(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    other = await create_agent(owner, agent["project_id"], name="Back office")
    await calling_on(owner, other, credential["id"])
    archived = await archive_project(owner, agent["project_id"])
    assert archived.status_code == 200, archived.text

    response = await delete_project_permanently(owner, agent["project_id"], archived.json()["name"])

    assert response.status_code == 202, response.text
    assert voice_layer.remote_agents == {}
    # Nothing calls with the credential any more.
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, credential["id"]))
    assert deleted.status_code == 204, deleted.text


# Refusals


async def test_calling_cant_be_turned_on_without_a_voice_capable_credential(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    await added(owner, provider="openai")
    agent = await an_agent(owner)

    response = await change(owner, agent, calls_enabled=True)

    assert refusal(response) == (
        ["body", "calls_enabled"],
        "no_voice_credential",
        "The Organisation has no voice-capable Provider Credential, so the Agent can't take "
        "Calls. An Owner adds an ElevenLabs credential in Organisation settings, Credentials.",
    )
    assert await call_settings(owner, agent) == CALLS_OFF
    assert voice_layer.remote_agents == {}
    assert await audit_events(owner, CHANGED) == []


async def test_calling_needs_a_credential_and_a_voice_chosen(owner: SignedUpMember) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)

    no_credential = await change(owner, agent, calls_enabled=True)
    no_voice = await change(owner, agent, calls_enabled=True, call_credential_id=credential["id"])

    assert refusal(no_credential) == (
        ["body", "call_credential_id"],
        "missing",
        "Choose the voice-capable credential the Agent's Calls use.",
    )
    assert refusal(no_voice) == (
        ["body", "call_voice_id"],
        "missing",
        "Choose the voice the Agent speaks with.",
    )
    assert await call_settings(owner, agent) == CALLS_OFF


async def test_another_organisations_credential_is_refused(
    owner: SignedUpMember, tenant_factory: TenantFactory, voice_layer: FakeVoiceLayer
) -> None:
    stranger = await tenant_factory()
    theirs = await add_elevenlabs_credential(stranger)
    await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)

    response = await change(
        owner,
        agent,
        calls_enabled=True,
        call_credential_id=theirs["id"],
        call_voice_id="fake-voice-ada",
    )

    assert refusal(response) == (
        ["body", "call_credential_id"],
        "unknown_credential",
        "No Provider Credential with this ID in the Organisation.",
    )
    assert voice_layer.remote_agents == {}
    assert await call_settings(owner, agent) == CALLS_OFF


async def test_a_credential_without_the_voice_capability_is_refused(
    owner: SignedUpMember,
) -> None:
    await add_elevenlabs_credential(owner)
    chat = await added(owner, provider="openai")
    agent = await an_agent(owner)

    response = await change(owner, agent, call_credential_id=chat["id"])

    assert refusal(response) == (
        ["body", "call_credential_id"],
        "not_voice_capable",
        "This credential doesn't have the voice Capability, so it can't carry Calls.",
    )


async def test_a_voice_the_credential_doesnt_offer_is_refused(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)

    response = await change(
        owner,
        agent,
        calls_enabled=True,
        call_credential_id=credential["id"],
        call_voice_id="someone-elses-voice",
    )

    assert refusal(response) == (
        ["body", "call_voice_id"],
        "voice_unavailable",
        "The credential's ElevenLabs account doesn't offer this voice.",
    )
    assert voice_layer.remote_agents == {}
    assert await call_settings(owner, agent) == CALLS_OFF


async def test_nothing_is_saved_when_the_voice_layer_cant_set_the_agent_up(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    voice_layer.failing = True

    response = await change(
        owner,
        agent,
        calls_enabled=True,
        call_credential_id=credential["id"],
        call_voice_id="fake-voice-ada",
    )

    assert response.status_code == 502, response.text
    assert response.json() == {
        "detail": "ElevenLabs couldn't be reached with this credential. Check the credential in "
        "Organisation settings, Credentials, or try again shortly."
    }
    assert await call_settings(owner, agent) == CALLS_OFF
    assert await audit_events(owner, CHANGED) == []


async def test_a_failed_move_to_another_credential_keeps_the_old_remote_agent(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    first = await add_elevenlabs_credential(owner)
    second = await added(owner, provider="elevenlabs", api_key=ANOTHER_ELEVENLABS_KEY)
    agent = await an_agent(owner)
    await calling_on(owner, agent, first["id"])
    before = dict(voice_layer.remote_agents)
    voice_layer.failing = True

    response = await change(owner, agent, call_credential_id=second["id"])

    assert response.status_code == 502, response.text
    assert voice_layer.remote_agents == before
    assert (await call_settings(owner, agent))["call_credential_id"] == first["id"]


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"calls_enabled": "yes"}, "calls_enabled"),
        ({"call_voice_id": ""}, "call_voice_id"),
        ({"call_voice_id": "v" * 65}, "call_voice_id"),
        ({"spoken_greeting": "g" * 501}, "spoken_greeting"),
        ({"call_credential_id": "not-an-id"}, "call_credential_id"),
    ],
)
async def test_malformed_call_settings_are_refused(
    owner: SignedUpMember, fields: dict[str, Any], field: str
) -> None:
    agent = await an_agent(owner)

    response = await change(owner, agent, **fields)

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", field]


# The credential is a Credential reference


async def test_a_credential_an_agent_calls_with_cant_be_deleted(
    owner: SignedUpMember,
) -> None:
    credential = await add_elevenlabs_credential(owner)
    agent = await an_agent(owner)
    await calling_on(owner, agent, credential["id"])
    path = credentials_path(owner.organisation_id, credential["id"])

    blocked = await owner.client.delete(path)

    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["references"] == [
        {"kind": "agent", "id": agent["id"], "name": "Front desk (Call settings)"}
    ]
    await change(owner, agent, calls_enabled=False)
    allowed = await owner.client.delete(path)
    assert allowed.status_code == 204, allowed.text
    # The Agent forgets the deleted credential.
    assert (await call_settings(owner, agent))["call_credential_id"] is None


# The voices route


def voices_path(organisation_id: str, credential_id: str) -> str:
    return credentials_path(organisation_id, credential_id) + "/voices"


async def test_an_editor_lists_a_credentials_voices(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    credential = await add_elevenlabs_credential(owner)

    response = await editor.client.get(voices_path(owner.organisation_id, credential["id"]))

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "id": "fake-voice-ada",
            "name": "Ada",
            "sample_url": "https://voices.example.invalid/fake-voice-ada.mp3",
        },
        {
            "id": "fake-voice-bryn",
            "name": "Bryn",
            "sample_url": "https://voices.example.invalid/fake-voice-bryn.mp3",
        },
        {"id": "fake-voice-cato", "name": "Cato", "sample_url": None},
    ]


async def test_a_credential_without_voice_has_no_voices(owner: SignedUpMember) -> None:
    chat = await added(owner, provider="openai")

    response = await owner.client.get(voices_path(owner.organisation_id, chat["id"]))

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "This credential doesn't have the voice Capability, so it has no voices."
    }


async def test_another_organisations_credential_has_no_voices_here(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    stranger = await tenant_factory()
    theirs = await add_elevenlabs_credential(stranger)

    response = await owner.client.get(voices_path(owner.organisation_id, theirs["id"]))
    unknown = await owner.client.get(voices_path(owner.organisation_id, str(uuid.uuid4())))

    assert response.status_code == 404, response.text
    assert unknown.status_code == 404, unknown.text


async def test_voices_cant_be_listed_while_the_voice_layer_is_down(
    owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    credential = await add_elevenlabs_credential(owner)
    voice_layer.failing = True

    response = await owner.client.get(voices_path(owner.organisation_id, credential["id"]))

    assert response.status_code == 502, response.text


# Tenancy


async def test_another_organisations_agent_is_unreachable(
    owner: SignedUpMember, tenant_factory: TenantFactory, voice_layer: FakeVoiceLayer
) -> None:
    stranger = await tenant_factory()
    credential = await add_elevenlabs_credential(stranger)
    agent = await an_agent(owner)

    response = await stranger.client.patch(
        agents_path(stranger, agent["project_id"], agent["id"], "operational-settings"),
        json={
            "calls_enabled": True,
            "call_credential_id": credential["id"],
            "call_voice_id": "fake-voice-ada",
        },
    )

    assert response.status_code == 404, response.text
    assert voice_layer.remote_agents == {}
    assert await call_settings(owner, agent) == CALLS_OFF
