"""API seam: Owners add, re-check, rotate and delete API-key Provider Credentials.

The credential verifier is the fake one (``CREDENTIAL_VERIFIER=fake``): it passes every key
except those starting ``fake-fail-<reason>``, so each test picks the check's outcome through
the key it saves. Everything is observed through the API, including Audit Events.
"""

import asyncio
import json
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.credentials.references import CredentialReference
from app.credentials.registry import Provider
from app.credentials.verifier import CheckFailure, CheckResult
from app.tenancy.repository import OrganisationScope
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock

ANTHROPIC_KEY = "sk-ant-api03-test-only-0000000000000000000000-abcd"
OPENAI_KEY = "sk-proj-test-only-1111111111111111111111111111-wxyz"
VOYAGE_KEY = "pa-test-only-2222222222222222222222222222222-9876"


def credentials_path(organisation_id: str, *rest: str) -> str:
    return "/".join([f"/api/organisations/{organisation_id}/credentials", *rest])


async def add_credential(
    owner: SignedUpMember,
    *,
    provider: str = "anthropic",
    api_key: str = ANTHROPIC_KEY,
    name: str | None = None,
    **extra: Any,
) -> httpx.Response:
    body = {
        "name": name or f"{provider} {uuid.uuid4().hex[:8]}",
        "provider": provider,
        "api_key": api_key,
        **extra,
    }
    return await owner.client.post(credentials_path(owner.organisation_id), json=body)


async def added(owner: SignedUpMember, **kwargs: Any) -> dict[str, Any]:
    response = await add_credential(owner, **kwargs)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def listed(member: SignedUpMember) -> list[dict[str, Any]]:
    response = await member.client.get(credentials_path(member.organisation_id))
    assert response.status_code == 200, response.text
    body: list[dict[str, Any]] = response.json()
    return body


async def audit_events(owner: SignedUpMember, action: str) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events", params={"action": action}
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# Adding


@pytest.mark.parametrize(
    ("provider", "api_key", "capabilities", "suffix"),
    [
        ("anthropic", ANTHROPIC_KEY, ["chat"], "abcd"),
        ("openai", OPENAI_KEY, ["chat", "embeddings"], "wxyz"),
        ("voyage", VOYAGE_KEY, ["embeddings", "rerank"], "9876"),
    ],
)
async def test_an_owner_adds_an_api_key_credential_for_each_provider(
    provider: str,
    api_key: str,
    capabilities: list[str],
    suffix: str,
    owner: SignedUpMember,
    clock: ControllableClock,
) -> None:
    response = await add_credential(owner, provider=provider, api_key=api_key, name="Marketing")

    assert response.status_code == 201, response.text
    credential = response.json()
    assert credential == {
        "id": credential["id"],
        "name": "Marketing",
        "provider": provider,
        "auth_kind": "api_key",
        "masked_suffix": suffix,
        "role_arn": None,
        "region": None,
        "capabilities": capabilities,
        "check_status": "passed",
        "check_failure": None,
        "last_checked_at": "2026-11-05T09:00:00Z",
        "created_at": credential["created_at"],
    }
    assert await listed(owner) == [credential]
    one = await owner.client.get(credentials_path(owner.organisation_id, credential["id"]))
    assert one.json() == credential
    (event,) = await audit_events(owner, "credential.created")
    assert event["actor"]["id"] == owner.member_id
    assert event["target"] == {"type": "provider_credential", "id": credential["id"]}
    assert event["after"] == {
        "name": "Marketing",
        "provider": provider,
        "auth_kind": "api_key",
        "capabilities": capabilities,
        "masked_suffix": suffix,
    }


async def test_a_credential_can_be_limited_to_some_of_its_providers_capabilities(
    owner: SignedUpMember,
) -> None:
    credential = await added(
        owner, provider="openai", api_key=OPENAI_KEY, capabilities=["embeddings", "chat"]
    )
    embeddings_only = await added(
        owner, provider="openai", api_key=OPENAI_KEY, capabilities=["embeddings"]
    )

    # Always in the registry's order.
    assert credential["capabilities"] == ["chat", "embeddings"]
    assert embeddings_only["capabilities"] == ["embeddings"]


async def test_a_capability_the_provider_lacks_is_refused(owner: SignedUpMember) -> None:
    response = await add_credential(owner, provider="anthropic", capabilities=["chat", "rerank"])

    assert response.status_code == 422
    assert response.json() == {"detail": "Anthropic credentials don't offer rerank."}
    assert await listed(owner) == []


async def test_bedrock_is_not_an_api_key_provider(owner: SignedUpMember) -> None:
    response = await add_credential(owner, provider="bedrock")

    assert response.status_code == 422
    assert await listed(owner) == []


@pytest.mark.parametrize(
    "api_key", ["short", "has a space in the middle-0000", "x" * 513, "line\nbreak-00000000"]
)
async def test_a_malformed_key_is_refused_without_echoing_it(
    api_key: str, owner: SignedUpMember
) -> None:
    response = await add_credential(owner, api_key=api_key)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "An API key is 8 to 512 characters, with no spaces or line breaks."
    }
    assert api_key not in response.text


async def test_surrounding_whitespace_is_trimmed_from_a_key(owner: SignedUpMember) -> None:
    credential = await added(owner, api_key=f"  {ANTHROPIC_KEY}\n")

    assert credential["masked_suffix"] == "abcd"


async def test_names_are_unique_within_an_organisation(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier
    await added(owner, name="Legal OpenAI", provider="openai", api_key=OPENAI_KEY)
    other = await tenant_factory()

    taken = await add_credential(owner, name="  Legal OpenAI ", provider="openai")
    elsewhere = await add_credential(other, name="Legal OpenAI", provider="openai")

    assert taken.status_code == 409
    assert taken.json() == {
        "detail": "Another credential in this Organisation already has that name."
    }
    assert elsewhere.status_code == 201
    # A taken name is refused before the key is sent to the provider.
    assert len(verifier.checked) == 2


class _AddsTheSameNameWhileChecking:
    """A verifier that, while checking the first key, lets another request take the name."""

    def __init__(self, owner: SignedUpMember, name: str) -> None:
        self._owner, self._name = owner, name
        self._raced = False

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        if not self._raced:
            self._raced = True
            response = await add_credential(self._owner, name=self._name)
            assert response.status_code == 201, response.text
        return CheckResult()


async def test_a_name_taken_while_the_key_was_being_checked_is_refused(
    app: FastAPI, owner: SignedUpMember
) -> None:
    app.state.credential_verifier = _AddsTheSameNameWhileChecking(owner, "Raced")

    response = await add_credential(owner, name="Raced")

    assert response.status_code == 409
    assert [c["name"] for c in await listed(owner)] == ["Raced"]


async def test_each_organisation_sees_only_its_own_credentials(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    mine = await added(owner, name="Mine")
    theirs = await added(other, name="Theirs")

    assert await listed(owner) == [mine]
    assert await listed(other) == [theirs]


async def test_credentials_are_listed_by_name(owner: SignedUpMember) -> None:
    for name in ("Marketing OpenAI", "Legal OpenAI", "Embeddings"):
        await added(owner, name=name, provider="openai", api_key=OPENAI_KEY)

    assert [c["name"] for c in await listed(owner)] == [
        "Embeddings",
        "Legal OpenAI",
        "Marketing OpenAI",
    ]


# Failed checks


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        ("invalid_key", "The provider rejected this API key. Check it was copied in full."),
        (
            "missing_model_access",
            "The key works, but it can't use this provider's models. "
            "Check the key's permissions in your provider account.",
        ),
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
    api_key = f"fake-fail-{reason}-0000-k3y9"

    response = await add_credential(owner, name="Broken", api_key=api_key)

    assert response.status_code == 400
    assert response.json() == {"detail": detail, "reason": reason}
    assert await listed(owner) == []
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["target"] == {"type": "provider_credential", "id": None}
    assert event["after"] == {"name": "Broken", "provider": "anthropic", "reason": reason}
    assert event["actor"]["id"] == owner.member_id
    # No characters of the rejected key reach the audit trail.
    assert "k3y9" not in json.dumps(event)


async def test_an_unknown_fake_failure_is_an_invalid_key(owner: SignedUpMember) -> None:
    response = await add_credential(owner, api_key="fake-fail-something-else")

    assert response.json()["reason"] == "invalid_key"


async def test_a_failed_check_does_not_hold_the_name(owner: SignedUpMember) -> None:
    await add_credential(owner, name="Retry", api_key="fake-fail-invalid_key-000")

    retried = await add_credential(owner, name="Retry")

    assert retried.status_code == 201


# Re-checking


class _Switchable:
    """A verifier whose answer the test changes between calls."""

    def __init__(self) -> None:
        self.result = CheckResult()
        self.checked: list[tuple[Provider, str]] = []

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        self.checked.append((provider, api_key))
        return self.result


async def test_an_owner_rechecks_a_credential_on_demand(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier
    credential = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    check = credentials_path(owner.organisation_id, credential["id"], "check")

    clock.advance(timedelta(hours=1))
    verifier.result = CheckResult(CheckFailure.QUOTA_EXCEEDED)
    failed = await owner.client.post(check)
    clock.advance(timedelta(hours=1))
    verifier.result = CheckResult()
    passed = await owner.client.post(check)

    assert failed.status_code == 200
    assert failed.json() | {"check_status": "failed", "check_failure": "quota_exceeded"} == (
        failed.json()
    )
    assert failed.json()["last_checked_at"] == "2026-11-05T10:00:00Z"
    assert passed.json()["check_status"] == "passed"
    assert passed.json()["check_failure"] is None
    assert passed.json()["last_checked_at"] == "2026-11-05T11:00:00Z"
    # The stored key is what gets checked again.
    assert verifier.checked == [(Provider.VOYAGE, VOYAGE_KEY)] * 3
    (failure,) = await audit_events(owner, "credential.check_failed")
    assert failure["target"] == {"type": "provider_credential", "id": credential["id"]}
    assert failure["after"]["reason"] == "quota_exceeded"
    (success,) = await audit_events(owner, "credential.checked")
    assert success["after"] == {"status": "passed"}


# Rotating


async def test_rotating_replaces_the_key_and_keeps_the_identity(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier
    credential = await added(owner, name="Support", provider="openai", api_key=OPENAI_KEY)
    new_key = "sk-proj-rotated-3333333333333333333333333333-n3w1"

    clock.advance(timedelta(days=30))
    rotated = await owner.client.post(
        credentials_path(owner.organisation_id, credential["id"], "rotate"),
        json={"api_key": new_key},
    )
    await owner.client.post(credentials_path(owner.organisation_id, credential["id"], "check"))

    assert rotated.status_code == 200, rotated.text
    assert rotated.json() == credential | {
        "masked_suffix": "n3w1",
        "last_checked_at": "2026-12-05T09:00:00Z",
    }
    assert await listed(owner) == [rotated.json()]
    # The re-check after rotating uses the new key.
    assert verifier.checked[-1] == (Provider.OPENAI, new_key)
    (event,) = await audit_events(owner, "credential.rotated")
    assert event["target"] == {"type": "provider_credential", "id": credential["id"]}
    assert (event["before"], event["after"]) == (
        {"masked_suffix": "wxyz"},
        {"masked_suffix": "n3w1"},
    )


async def test_a_rotation_that_fails_its_check_keeps_the_old_key(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier
    credential = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    verifier.result = CheckResult(CheckFailure.INVALID_KEY)
    response = await owner.client.post(
        credentials_path(owner.organisation_id, credential["id"], "rotate"),
        json={"api_key": "sk-ant-wrong-key-zzzz"},
    )
    verifier.result = CheckResult()
    await owner.client.post(credentials_path(owner.organisation_id, credential["id"], "check"))

    assert response.status_code == 400
    assert response.json()["reason"] == "invalid_key"
    assert await listed(owner) == [credential]
    assert verifier.checked[-1] == (Provider.ANTHROPIC, ANTHROPIC_KEY)
    assert await audit_events(owner, "credential.rotated") == []
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["after"]["masked_suffix"] == "abcd"
    assert "attempted_suffix" not in event["after"]
    # No characters of the rejected key reach the audit trail.
    assert "zzzz" not in json.dumps(event)


async def test_a_malformed_rotation_key_is_refused(owner: SignedUpMember) -> None:
    credential = await added(owner)

    response = await owner.client.post(
        credentials_path(owner.organisation_id, credential["id"], "rotate"),
        json={"api_key": "tiny"},
    )

    assert response.status_code == 422
    assert await listed(owner) == [credential]


# Deleting


async def test_an_owner_deletes_an_unused_credential(owner: SignedUpMember) -> None:
    credential = await added(owner, name="Old key")

    response = await owner.client.delete(credentials_path(owner.organisation_id, credential["id"]))

    assert response.status_code == 204
    assert await listed(owner) == []
    gone = await owner.client.get(credentials_path(owner.organisation_id, credential["id"]))
    assert gone.status_code == 404
    (event,) = await audit_events(owner, "credential.deleted")
    assert event["before"] == {
        "name": "Old key",
        "provider": "anthropic",
        "auth_kind": "api_key",
        "capabilities": ["chat"],
        "masked_suffix": "abcd",
    }


async def test_deleting_is_blocked_while_something_references_the_credential(
    app: FastAPI, owner: SignedUpMember
) -> None:
    in_use = await added(owner, name="In use")
    unused = await added(owner, name="Unused")
    users: dict[str, list[CredentialReference]] = {
        in_use["id"]: [
            CredentialReference("agent", "a-2", "Support bot"),
            CredentialReference("project", "p-1", "Handbook"),
            CredentialReference("agent", "a-1", "Sales bot"),
        ]
    }
    seen_scopes: list[OrganisationScope] = []

    async def test_references(
        session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
    ) -> list[CredentialReference]:
        seen_scopes.append(scope)
        return users.get(str(credential_id), [])

    unregister = app.state.credential_references.register(test_references)
    blocked = await owner.client.delete(credentials_path(owner.organisation_id, in_use["id"]))
    allowed = await owner.client.delete(credentials_path(owner.organisation_id, unused["id"]))
    users.clear()
    after_release = await owner.client.delete(credentials_path(owner.organisation_id, in_use["id"]))
    unregister()

    assert blocked.status_code == 409
    assert blocked.json() == {
        "detail": "This credential is still in use. Move these items to another credential first.",
        "references": [
            {"kind": "agent", "id": "a-1", "name": "Sales bot"},
            {"kind": "agent", "id": "a-2", "name": "Support bot"},
            {"kind": "project", "id": "p-1", "name": "Handbook"},
        ],
    }
    assert allowed.status_code == 204
    assert after_release.status_code == 204
    assert {str(scope.organisation_id) for scope in seen_scopes} == {owner.organisation_id}
    assert len(await audit_events(owner, "credential.deleted")) == 2


async def test_references_from_several_consumers_are_combined(
    app: FastAPI, owner: SignedUpMember
) -> None:
    credential = await added(owner)

    async def projects(*_: Any) -> list[CredentialReference]:
        return [CredentialReference("project", "p-1", "Handbook")]

    async def guardrails(*_: Any) -> list[CredentialReference]:
        return [CredentialReference("guardrail", "g-1", "Classifier")]

    removers = [app.state.credential_references.register(s) for s in (projects, guardrails)]
    blocked = await owner.client.delete(credentials_path(owner.organisation_id, credential["id"]))
    for remove in removers:
        remove()
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, credential["id"]))

    assert [r["kind"] for r in blocked.json()["references"]] == ["guardrail", "project"]
    assert deleted.status_code == 204


# Not found


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("POST", "/check", None),
        ("POST", "/rotate", {"api_key": OPENAI_KEY}),
        ("DELETE", "", None),
    ],
)
async def test_an_unknown_credential_is_not_found(
    method: str, suffix: str, body: dict[str, str] | None, owner: SignedUpMember
) -> None:
    path = credentials_path(owner.organisation_id, str(uuid.uuid4())) + suffix

    response = await owner.client.request(method, path, json=body)

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


# Roles


async def test_editors_see_credentials_but_cannot_manage_them(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    credential = await added(owner, name="Shared")
    editor = await member_factory(owner, "editor")
    one = credentials_path(owner.organisation_id, credential["id"])

    assert await listed(editor) == [credential]
    assert (await editor.client.get(one)).json() == credential
    refused = [
        await add_credential(editor),
        await editor.client.post(f"{one}/check"),
        await editor.client.post(f"{one}/rotate", json={"api_key": ANTHROPIC_KEY}),
        await editor.client.delete(one),
    ]
    assert [(r.status_code, r.json()) for r in refused] == [
        (403, {"detail": "Only Owners can do this"})
    ] * 4
    assert await listed(owner) == [credential]


# Capability registry


async def test_the_capability_registry_lists_providers_capabilities_and_models(
    owner: SignedUpMember,
) -> None:
    response = await owner.client.get("/api/providers")

    assert response.status_code == 200
    providers = {p["id"]: p for p in response.json()}
    assert list(providers) == ["anthropic", "openai", "bedrock", "voyage", "demo"]
    summary = {
        provider_id: (
            provider["auth_kinds"],
            [c["capability"] for c in provider["capabilities"]],
        )
        for provider_id, provider in providers.items()
    }
    assert summary == {
        "anthropic": (["api_key"], ["chat"]),
        "openai": (["api_key"], ["chat", "embeddings"]),
        "bedrock": (["aws_role", "aws_access_keys"], ["chat", "embeddings", "rerank"]),
        "voyage": (["api_key"], ["embeddings", "rerank"]),
        "demo": (["api_key"], ["chat"]),
    }
    openai = providers["openai"]
    assert openai["name"] == "OpenAI"
    embeddings = next(c for c in openai["capabilities"] if c["capability"] == "embeddings")
    assert {
        "id": "text-embedding-3-small",
        "name": "text-embedding-3-small",
        "supports_tools": False,
    } in embeddings["models"]
    for provider in providers.values():
        for capability in provider["capabilities"]:
            assert capability["models"], (provider["id"], capability["capability"])


async def test_the_capability_registry_needs_a_signed_in_member(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/providers")).status_code == 401


# Concurrency


async def test_concurrent_rotations_each_leave_a_working_key(
    app: FastAPI, owner: SignedUpMember
) -> None:
    verifier = _Switchable()
    app.state.credential_verifier = verifier
    credential = await added(owner)
    path = credentials_path(owner.organisation_id, credential["id"], "rotate")
    keys = [f"sk-ant-concurrent-{i}-000000000000-{i:04d}" for i in range(4)]

    responses = await asyncio.gather(
        *(owner.client.post(path, json={"api_key": key}) for key in keys)
    )
    await owner.client.post(credentials_path(owner.organisation_id, credential["id"], "check"))

    assert {r.status_code for r in responses} == {200}
    (final,) = await listed(owner)
    # The stored key opens and matches the suffix shown.
    assert verifier.checked[-1][1].endswith(final["masked_suffix"])
