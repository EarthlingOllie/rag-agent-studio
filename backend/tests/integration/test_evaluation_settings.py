"""API seam: the Organisation's Evaluation Model and Evaluation repeats (Organisation settings,
Models).

Every Member reads them; only Owners change them, and each change is an Audit Event with its
before and after values. The Evaluation Model is a Credential reference, so its credential can't
be deleted while it is chosen. Everything is observed through the API.
"""

from typing import Any

import pytest

from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    audit_events,
    credentials_path,
)


def settings_path(member: SignedUpMember, *rest: str) -> str:
    return "/".join([f"/api/organisations/{member.organisation_id}", *rest])


async def evaluation_settings(member: SignedUpMember) -> Any:
    response = await member.client.get(settings_path(member, "evaluation-settings"))
    assert response.status_code == 200, response.text
    return response.json()


async def set_evaluation_model(
    member: SignedUpMember, credential_id: str | None, model: str | None
) -> Any:
    return await member.client.put(
        settings_path(member, "evaluation-model"),
        json={"credential_id": credential_id, "model": model},
    )


async def set_repeats(member: SignedUpMember, repeats: int) -> Any:
    return await member.client.put(
        settings_path(member, "evaluation-repeats"), json={"repeats": repeats}
    )


async def test_an_organisation_starts_judging_with_the_default_model_three_times(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    assert await evaluation_settings(editor) == {"evaluation_model": None, "repeats": 3}


async def test_an_owner_sets_the_repeats_to_an_odd_number_up_to_nine(
    owner: SignedUpMember,
) -> None:
    for repeats in (1, 5, 7, 9, 3):
        response = await set_repeats(owner, repeats)
        assert response.status_code == 200, response.text
        assert response.json() == {"evaluation_model": None, "repeats": repeats}

    for refused in (0, 2, 4, 6, 8, 10, 11):
        assert (await set_repeats(owner, refused)).status_code == 422
    assert (await evaluation_settings(owner))["repeats"] == 3


async def test_changing_the_repeats_is_audited_with_before_and_after(
    owner: SignedUpMember,
) -> None:
    await set_repeats(owner, 5)
    await set_repeats(owner, 5)
    await set_repeats(owner, 1)

    later, earlier = await audit_events(owner, "organisation.evaluation_repeats_changed")
    assert earlier["actor"]["id"] == owner.member_id
    assert earlier["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert (earlier["before"], earlier["after"]) == ({"repeats": 3}, {"repeats": 5})
    assert (later["before"], later["after"]) == ({"repeats": 5}, {"repeats": 1})


async def test_an_owner_chooses_the_evaluation_model_and_goes_back_to_the_default(
    owner: SignedUpMember,
) -> None:
    claude = await added(owner, name="Claude")

    chosen = await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")

    assert chosen.status_code == 200, chosen.text
    model = {
        "credential_id": claude["id"],
        "credential_name": "Claude",
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "model_name": "Claude Haiku 4.5",
    }
    assert chosen.json() == {"evaluation_model": model, "repeats": 3}
    assert await evaluation_settings(owner) == chosen.json()

    back = await set_evaluation_model(owner, None, None)

    assert back.status_code == 200, back.text
    assert back.json() == {"evaluation_model": None, "repeats": 3}


async def test_changing_the_evaluation_model_is_audited_with_before_and_after(
    owner: SignedUpMember,
) -> None:
    claude = await added(owner, name="Claude")
    gpt = await added(owner, provider="openai", api_key=OPENAI_KEY, name="GPT")

    await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")
    await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")
    await set_evaluation_model(owner, gpt["id"], "gpt-4.1")
    await set_evaluation_model(owner, None, None)
    await set_evaluation_model(owner, None, None)

    back, moved, first = await audit_events(owner, "organisation.evaluation_model_changed")
    haiku = {
        "credential_id": claude["id"],
        "credential_name": "Claude",
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
    }
    gpt_41 = {
        "credential_id": gpt["id"],
        "credential_name": "GPT",
        "provider": "openai",
        "model": "gpt-4.1",
    }
    assert first["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert (first["before"], first["after"]) == (None, haiku)
    assert (moved["before"], moved["after"]) == (haiku, gpt_41)
    assert (back["before"], back["after"]) == (gpt_41, None)


@pytest.mark.parametrize(
    ("provider", "api_key", "capabilities", "model", "detail"),
    [
        (
            "voyage",
            VOYAGE_KEY,
            None,
            "voyage-3.5",
            "That credential can't be used for chat. Choose a chat-capable credential.",
        ),
        (
            "openai",
            OPENAI_KEY,
            ["embeddings"],
            "gpt-4.1",
            "That credential can't be used for chat. Choose a chat-capable credential.",
        ),
        ("openai", OPENAI_KEY, None, "gpt-0", "OpenAI doesn't offer gpt-0 for chat."),
    ],
)
async def test_only_a_chat_model_of_a_chat_capable_credential_can_judge(
    owner: SignedUpMember,
    provider: str,
    api_key: str,
    capabilities: list[str] | None,
    model: str,
    detail: str,
) -> None:
    kwargs: dict[str, Any] = {"provider": provider, "api_key": api_key}
    if capabilities is not None:
        kwargs["capabilities"] = capabilities
    credential = await added(owner, **kwargs)

    refused = await set_evaluation_model(owner, credential["id"], model)

    assert (refused.status_code, refused.json()) == (422, {"detail": detail})
    assert (await evaluation_settings(owner))["evaluation_model"] is None
    assert await audit_events(owner, "organisation.evaluation_model_changed") == []


async def test_a_credential_from_elsewhere_or_half_a_choice_is_refused(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    stranger = await tenant_factory()
    theirs = await added(stranger, name="Theirs")
    mine = await added(owner, name="Claude")

    elsewhere = await set_evaluation_model(owner, theirs["id"], "claude-haiku-4-5")
    no_model = await set_evaluation_model(owner, mine["id"], None)
    no_credential = await set_evaluation_model(owner, None, "claude-haiku-4-5")

    assert (elsewhere.status_code, elsewhere.json()) == (
        422,
        {"detail": "Choose one of this Organisation's credentials."},
    )
    assert no_model.status_code == no_credential.status_code == 422
    assert (await evaluation_settings(owner))["evaluation_model"] is None


async def test_editors_cannot_change_the_evaluation_model_or_repeats(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    claude = await added(owner, name="Claude")

    model = await set_evaluation_model(editor, claude["id"], "claude-haiku-4-5")
    repeats = await set_repeats(editor, 5)

    assert model.status_code == repeats.status_code == 403
    assert await evaluation_settings(owner) == {"evaluation_model": None, "repeats": 3}


async def test_the_evaluation_models_credential_cannot_be_deleted_while_chosen(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    claude = await added(owner, name="Claude")
    await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")
    # Another Organisation's Evaluation Model doesn't reference this one's credentials.
    stranger = await tenant_factory()
    await set_evaluation_model(stranger, (await added(stranger))["id"], "claude-haiku-4-5")

    blocked = await owner.client.delete(credentials_path(owner.organisation_id, claude["id"]))

    assert blocked.status_code == 409
    assert blocked.json()["references"] == [
        {
            "kind": "evaluation_model",
            "id": owner.organisation_id,
            "name": "Evaluation Model (Claude Haiku 4.5)",
        }
    ]
    await set_evaluation_model(owner, None, None)
    released = await owner.client.delete(credentials_path(owner.organisation_id, claude["id"]))
    assert released.status_code == 204
