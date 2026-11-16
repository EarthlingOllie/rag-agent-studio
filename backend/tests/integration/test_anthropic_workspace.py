"""API seam: an Anthropic credential names the workspace its key works in.

A personal or service account key that isn't scoped to one workspace must send
``anthropic-workspace-id`` on every request. The Owner gives the Workspace ID with the key; the
check, every re-check and every model call then name it (the model gateway's own test covers
the calls). A recording verifier stands in for the provider.
"""

from typing import Any

import pytest
from fastapi import FastAPI

from app.credentials.registry import Provider
from app.credentials.verifier import CheckFailure, CheckResult
from tests.conftest import SignedUpMember
from tests.integration.test_provider_credentials import (
    ANTHROPIC_KEY,
    OPENAI_KEY,
    add_credential,
    added,
    audit_events,
    credentials_path,
    listed,
)

WORKSPACE = "wrkspc_01JwQvzr7rXLA5AGx3HKfFUJ"
OTHER_WORKSPACE = "wrkspc_02KxRwas8sYMB6BHy4ILgGVK"
NEW_KEY = "sk-ant-api03-rotated-4444444444444444444444-r0t8"


class _Recording:
    """A verifier that records what it was asked to check, and answers ``result``."""

    def __init__(self) -> None:
        self.result = CheckResult()
        self.checked: list[tuple[Provider, str, str | None]] = []

    async def check(
        self, provider: Provider, api_key: str, *, workspace_id: str | None = None
    ) -> CheckResult:
        self.checked.append((provider, api_key, workspace_id))
        return self.result


@pytest.fixture
def verifier(app: FastAPI) -> _Recording:
    recording = _Recording()
    app.state.credential_verifier = recording
    return recording


async def rotate(owner: SignedUpMember, credential_id: str, **body: Any) -> Any:
    return await owner.client.post(
        credentials_path(owner.organisation_id, credential_id, "rotate"), json=body
    )


# Adding


async def test_an_owner_adds_an_anthropic_key_with_its_workspace(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner, name="Personal Claude", workspace_id=WORKSPACE)

    assert credential["workspace_id"] == WORKSPACE
    assert await listed(owner) == [credential]
    # The key is checked in that workspace.
    assert verifier.checked == [(Provider.ANTHROPIC, ANTHROPIC_KEY, WORKSPACE)]
    (event,) = await audit_events(owner, "credential.created")
    assert event["after"]["workspace_id"] == WORKSPACE


async def test_a_key_scoped_to_one_workspace_needs_no_workspace_id(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner)

    assert credential["workspace_id"] is None
    assert verifier.checked == [(Provider.ANTHROPIC, ANTHROPIC_KEY, None)]
    (event,) = await audit_events(owner, "credential.created")
    assert "workspace_id" not in event["after"]


async def test_surrounding_whitespace_is_trimmed_from_a_workspace_id(
    owner: SignedUpMember,
) -> None:
    credential = await added(owner, workspace_id=f"  {WORKSPACE}\n")

    assert credential["workspace_id"] == WORKSPACE


@pytest.mark.parametrize(
    "workspace_id",
    ["01JwQvzr7rXLA5AGx3HKfFUJ", "wrkspc_", "wrkspc_has spaces", "wrkspc_" + "a" * 58],
)
async def test_a_malformed_workspace_id_is_refused(
    owner: SignedUpMember, verifier: _Recording, workspace_id: str
) -> None:
    response = await add_credential(owner, workspace_id=workspace_id)

    assert response.status_code == 422
    assert verifier.checked == []
    assert await listed(owner) == []


async def test_only_anthropic_credentials_take_a_workspace_id(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    response = await add_credential(
        owner, provider="openai", api_key=OPENAI_KEY, workspace_id=WORKSPACE
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Only Anthropic credentials take a Workspace ID."}
    assert verifier.checked == []


@pytest.mark.parametrize(
    ("failure", "detail"),
    [
        (
            CheckFailure.WORKSPACE_REQUIRED,
            "This key isn't scoped to one workspace, so Anthropic needs to know which to use. "
            "Add the Workspace ID, or use a key scoped to a workspace.",
        ),
        (
            CheckFailure.UNKNOWN_WORKSPACE,
            "Anthropic doesn't know this Workspace ID, or the key can't use that workspace. "
            "Copy the ID from the Workspaces page of the Claude Console.",
        ),
    ],
)
async def test_a_workspace_failure_says_what_to_do_and_stores_nothing(
    owner: SignedUpMember, verifier: _Recording, failure: CheckFailure, detail: str
) -> None:
    verifier.result = CheckResult(failure)

    response = await add_credential(owner, name="Unscoped", workspace_id=WORKSPACE)

    assert response.status_code == 400
    assert response.json() == {"detail": detail, "reason": failure.value}
    assert await listed(owner) == []
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["after"] == {
        "name": "Unscoped",
        "provider": "anthropic",
        "masked_suffix": "abcd",
        "workspace_id": WORKSPACE,
        "reason": failure.value,
    }


async def test_a_failed_recheck_records_the_workspace(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner, workspace_id=WORKSPACE)
    verifier.result = CheckResult(CheckFailure.UNKNOWN_WORKSPACE)

    response = await owner.client.post(
        credentials_path(owner.organisation_id, credential["id"], "check")
    )

    assert response.json()["check_failure"] == "unknown_workspace"
    # The stored key is checked again in its workspace.
    assert verifier.checked[-1] == (Provider.ANTHROPIC, ANTHROPIC_KEY, WORKSPACE)
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["after"]["workspace_id"] == WORKSPACE


# Rotating


async def test_rotating_without_a_workspace_id_keeps_the_credentials_workspace(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner, workspace_id=WORKSPACE)

    response = await rotate(owner, credential["id"], api_key=NEW_KEY)

    assert response.status_code == 200, response.text
    assert response.json()["workspace_id"] == WORKSPACE
    assert verifier.checked[-1] == (Provider.ANTHROPIC, NEW_KEY, WORKSPACE)
    (event,) = await audit_events(owner, "credential.rotated")
    assert (event["before"], event["after"]) == (
        {"masked_suffix": "abcd"},
        {"masked_suffix": "r0t8"},
    )


async def test_rotating_to_another_workspace_moves_the_credential(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner, workspace_id=WORKSPACE)

    response = await rotate(owner, credential["id"], api_key=NEW_KEY, workspace_id=OTHER_WORKSPACE)

    assert response.json()["workspace_id"] == OTHER_WORKSPACE
    assert verifier.checked[-1] == (Provider.ANTHROPIC, NEW_KEY, OTHER_WORKSPACE)
    await owner.client.post(credentials_path(owner.organisation_id, credential["id"], "check"))
    assert verifier.checked[-1] == (Provider.ANTHROPIC, NEW_KEY, OTHER_WORKSPACE)
    (event,) = await audit_events(owner, "credential.rotated")
    assert (event["before"], event["after"]) == (
        {"masked_suffix": "abcd", "workspace_id": WORKSPACE},
        {"masked_suffix": "r0t8", "workspace_id": OTHER_WORKSPACE},
    )


async def test_rotating_to_a_key_scoped_to_one_workspace_clears_the_workspace_id(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner, workspace_id=WORKSPACE)

    response = await rotate(owner, credential["id"], api_key=NEW_KEY, workspace_id=None)

    assert response.json()["workspace_id"] is None
    assert verifier.checked[-1] == (Provider.ANTHROPIC, NEW_KEY, None)


async def test_a_rotation_into_a_workspace_that_fails_its_check_keeps_the_old_one(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner)
    verifier.result = CheckResult(CheckFailure.UNKNOWN_WORKSPACE)

    response = await rotate(owner, credential["id"], api_key=NEW_KEY, workspace_id=WORKSPACE)

    assert response.status_code == 400
    assert response.json()["reason"] == "unknown_workspace"
    assert await listed(owner) == [credential]
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["after"]["attempted_workspace_id"] == WORKSPACE
    assert event["after"]["attempted_suffix"] == "r0t8"


async def test_another_providers_credential_cant_be_rotated_into_a_workspace(
    owner: SignedUpMember, verifier: _Recording
) -> None:
    credential = await added(owner, provider="openai", api_key=OPENAI_KEY)

    response = await rotate(owner, credential["id"], api_key=OPENAI_KEY, workspace_id=WORKSPACE)

    assert response.status_code == 422
    assert response.json() == {"detail": "Only Anthropic credentials take a Workspace ID."}
    assert await listed(owner) == [credential]
