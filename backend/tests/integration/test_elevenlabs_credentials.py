"""API seam: Owners add ElevenLabs Provider Credentials, which offer the voice Capability.

The credential verifier is the fake one (``CREDENTIAL_VERIFIER=fake``): it passes every key
except those starting ``fake-fail-<reason>``. Tests that need to see what was checked put a
recording verifier on ``app.state``. Everything is observed through the API, including Audit
Events.
"""

from datetime import timedelta

import pytest
from fastapi import FastAPI

from app.credentials.registry import Provider
from app.credentials.verifier import CheckFailure, CheckResult
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_provider_credentials import (
    _Switchable,
    add_credential,
    added,
    audit_events,
    credentials_path,
    listed,
)

ELEVENLABS_KEY = "sk_test_only_3333333333333333333333333333333333-e1ev"
INVALID_KEY = (
    "ElevenLabs rejected this API key. Check it was copied in full, and that its permissions "
    "allow ElevenLabs Agents."
)


async def add_elevenlabs(owner: SignedUpMember, **kwargs: object) -> dict[str, object]:
    return await added(owner, provider="elevenlabs", api_key=ELEVENLABS_KEY, **kwargs)


async def test_an_owner_adds_an_elevenlabs_credential_with_the_voice_capability(
    owner: SignedUpMember,
) -> None:
    response = await add_credential(
        owner, provider="elevenlabs", api_key=ELEVENLABS_KEY, name="Calls"
    )

    assert response.status_code == 201, response.text
    credential = response.json()
    assert credential == {
        "id": credential["id"],
        "name": "Calls",
        "provider": "elevenlabs",
        "auth_kind": "api_key",
        "masked_suffix": "e1ev",
        "role_arn": None,
        "region": None,
        "capabilities": ["voice"],
        "check_status": "passed",
        "check_failure": None,
        "last_checked_at": "2026-11-05T09:00:00Z",
        "created_at": credential["created_at"],
    }
    # Only the masked suffix is ever shown: never the key.
    assert ELEVENLABS_KEY not in response.text
    assert ELEVENLABS_KEY not in str(await listed(owner))
    (event,) = await audit_events(owner, "credential.created")
    assert event["after"] == {
        "name": "Calls",
        "provider": "elevenlabs",
        "auth_kind": "api_key",
        "capabilities": ["voice"],
        "masked_suffix": "e1ev",
    }


async def test_the_key_is_checked_with_elevenlabs(app: FastAPI, owner: SignedUpMember) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier

    await add_elevenlabs(owner)

    assert verifier.checked == [(Provider.ELEVENLABS, ELEVENLABS_KEY)]


@pytest.mark.parametrize("capability", ["chat", "embeddings", "rerank"])
async def test_elevenlabs_offers_only_voice(capability: str, owner: SignedUpMember) -> None:
    response = await add_credential(
        owner, provider="elevenlabs", api_key=ELEVENLABS_KEY, capabilities=[capability]
    )

    assert response.status_code == 422
    assert response.json() == {"detail": f"ElevenLabs credentials don't offer {capability}."}
    assert await listed(owner) == []


async def test_no_model_provider_offers_voice(owner: SignedUpMember) -> None:
    response = await add_credential(owner, provider="openai", capabilities=["chat", "voice"])

    assert response.status_code == 422
    assert response.json() == {"detail": "OpenAI credentials don't offer voice."}


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        ("invalid_key", INVALID_KEY),
        (
            "quota_exceeded",
            "The provider says this key is over its rate limit or quota. "
            "Try again later, or check your plan.",
        ),
        (
            "provider_unreachable",
            "We couldn't reach the provider to check the key. Try again in a few minutes.",
        ),
    ],
)
async def test_a_failed_check_gives_a_typed_reason_and_stores_nothing(
    reason: str, detail: str, owner: SignedUpMember
) -> None:
    response = await add_credential(
        owner, provider="elevenlabs", name="Broken", api_key=f"fake-fail-{reason}-0000-v01c"
    )

    assert response.status_code == 400
    assert response.json() == {"detail": detail, "reason": reason}
    assert await listed(owner) == []
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["after"] == {
        "name": "Broken",
        "provider": "elevenlabs",
        "masked_suffix": "v01c",
        "reason": reason,
    }


async def test_an_elevenlabs_key_is_rotated_and_rechecked_like_any_other(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier
    credential = await add_elevenlabs(owner, name="Calls")
    one = credentials_path(owner.organisation_id, str(credential["id"]))
    new_key = "sk_test_only_rotated_44444444444444444444444444-n3wk"

    clock.advance(timedelta(days=1))
    verifier.result = CheckResult(CheckFailure.INVALID_KEY)
    refused = await owner.client.post(f"{one}/rotate", json={"api_key": "sk_wrong_key_0000-bad0"})
    verifier.result = CheckResult()
    rotated = await owner.client.post(f"{one}/rotate", json={"api_key": new_key})
    clock.advance(timedelta(hours=1))
    verifier.result = CheckResult(CheckFailure.QUOTA_EXCEEDED)
    rechecked = await owner.client.post(f"{one}/check")

    assert refused.status_code == 400
    assert refused.json() == {"detail": INVALID_KEY, "reason": "invalid_key"}
    assert rotated.status_code == 200, rotated.text
    assert rotated.json() == credential | {
        "masked_suffix": "n3wk",
        "last_checked_at": "2026-11-06T09:00:00Z",
    }
    assert new_key not in rotated.text
    assert rechecked.json() | {"check_status": "failed", "check_failure": "quota_exceeded"} == (
        rechecked.json()
    )
    # The re-check opened the rotated key.
    assert verifier.checked[-1] == (Provider.ELEVENLABS, new_key)
    (rotation,) = await audit_events(owner, "credential.rotated")
    assert (rotation["before"], rotation["after"]) == (
        {"masked_suffix": "e1ev"},
        {"masked_suffix": "n3wk"},
    )
    assert len(await audit_events(owner, "credential.check_failed")) == 2


async def test_deleting_an_elevenlabs_credential_is_an_audit_event(owner: SignedUpMember) -> None:
    credential = await add_elevenlabs(owner, name="Calls")

    response = await owner.client.delete(
        credentials_path(owner.organisation_id, str(credential["id"]))
    )

    assert response.status_code == 204
    assert await listed(owner) == []
    (event,) = await audit_events(owner, "credential.deleted")
    assert event["target"] == {"type": "provider_credential", "id": credential["id"]}
    assert event["before"]["provider"] == "elevenlabs"
    assert event["before"]["capabilities"] == ["voice"]


async def test_editors_see_an_elevenlabs_credential_but_cannot_manage_it(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    credential = await add_elevenlabs(owner)
    editor = await member_factory(owner, "editor")
    one = credentials_path(owner.organisation_id, str(credential["id"]))

    assert await listed(editor) == [credential]
    refused = [
        await add_credential(editor, provider="elevenlabs", api_key=ELEVENLABS_KEY),
        await editor.client.post(f"{one}/check"),
        await editor.client.post(f"{one}/rotate", json={"api_key": ELEVENLABS_KEY}),
        await editor.client.delete(one),
    ]
    assert [r.status_code for r in refused] == [403] * 4
    assert await listed(owner) == [credential]


async def test_another_organisations_elevenlabs_credential_is_unreachable(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    theirs = await add_elevenlabs(other)
    # Their credential, through our Organisation's routes.
    one = credentials_path(owner.organisation_id, str(theirs["id"]))

    responses = [
        await owner.client.get(one),
        await owner.client.post(f"{one}/check"),
        await owner.client.post(f"{one}/rotate", json={"api_key": ELEVENLABS_KEY}),
        await owner.client.delete(one),
        await owner.client.get(f"{one}/models/voice"),
    ]

    assert [(r.status_code, r.json()) for r in responses] == [(404, {"detail": "Not found"})] * 5
    assert await listed(owner) == []
    assert await listed(other) == [theirs]


# Pickers


@pytest.mark.parametrize("capability", ["chat", "embeddings", "rerank"])
async def test_a_voice_credential_offers_no_model_to_a_picker(
    capability: str, owner: SignedUpMember
) -> None:
    credential = await add_elevenlabs(owner)

    response = await owner.client.get(
        credentials_path(owner.organisation_id, str(credential["id"]), "models", capability)
    )

    assert (response.status_code, response.json()) == (200, [])


async def test_a_voice_credential_is_not_an_embedding_model_choice(owner: SignedUpMember) -> None:
    await add_elevenlabs(owner)

    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/embedding-models"
    )

    assert response.status_code == 200
    assert [choice["credential_id"] for choice in response.json()] == [None]


async def test_a_voice_credential_cannot_be_the_default_model(owner: SignedUpMember) -> None:
    credential = await add_elevenlabs(owner)

    response = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/default-model",
        json={"credential_id": credential["id"], "model": "claude-sonnet-4-5"},
    )

    assert response.status_code == 422
    current = await owner.client.get(f"/api/organisations/{owner.organisation_id}/default-model")
    assert current.json() is None
