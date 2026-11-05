"""Signing in and out at the API seam."""

import httpx

from tests.conftest import ClientFactory, SignedUpMember, TenantFactory

SIGN_IN_FAILED = {"detail": "Email or password is incorrect"}


def _credentials(member: SignedUpMember) -> dict[str, str]:
    return {"email": member.email, "password": member.password}


async def test_a_member_signs_in_with_email_and_password(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    response = await client.post("/api/auth/sign-in", json=_credentials(owner))

    assert response.status_code == 200
    assert response.json() == {
        "member": {"id": owner.member_id, "name": owner.name, "email": owner.email},
        "organisations": [
            {
                "id": owner.organisation_id,
                "name": owner.organisation_name,
                "role": "owner",
                "mfa_required": False,
            }
        ],
        "active_organisation_id": owner.organisation_id,
    }
    assert (await client.get("/api/auth/me")).json() == response.json()


async def test_sign_in_ignores_the_case_and_surrounding_spaces_of_the_email(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    response = await client.post(
        "/api/auth/sign-in", json={"email": f" {owner.email.upper()} ", "password": owner.password}
    )

    assert response.status_code == 200


async def test_signing_in_rotates_the_session(
    owner: SignedUpMember, new_client: ClientFactory
) -> None:
    old_token = owner.client.cookies["studio_session"]

    response = await owner.client.post("/api/auth/sign-in", json=_credentials(owner))

    new_token = response.cookies["studio_session"]
    assert new_token != old_token
    assert (await owner.client.get("/api/auth/me")).status_code == 200
    replay = await new_client()
    replay.cookies.set("studio_session", old_token)
    assert (await replay.get("/api/auth/me")).status_code == 401


async def test_sign_in_errors_are_identical_whether_or_not_the_email_is_registered(
    owner: SignedUpMember, new_client: ClientFactory
) -> None:
    attempts = {
        "registered email, wrong password": {"email": owner.email, "password": "wrong password"},
        "unregistered email": {"email": f"nobody-{owner.email}", "password": owner.password},
        "unregistered email, wrong password": {
            "email": f"nobody-{owner.email}",
            "password": "wrong password",
        },
    }
    responses = {}
    for label, credentials in attempts.items():
        client = await new_client()
        responses[label] = await client.post("/api/auth/sign-in", json=credentials)

    observed = {
        (
            response.status_code,
            response.content,
            tuple(sorted((k, v) for k, v in response.headers.items() if k != "date")),
        )
        for response in responses.values()
    }
    assert len(observed) == 1
    (status, content, headers) = observed.pop()
    assert status == 401
    assert httpx.Response(status, content=content).json() == SIGN_IN_FAILED
    assert "set-cookie" not in dict(headers)


async def test_signing_out_ends_the_session_on_the_server(
    owner: SignedUpMember, new_client: ClientFactory
) -> None:
    token = owner.client.cookies["studio_session"]

    response = await owner.client.post("/api/auth/sign-out")

    assert response.status_code == 204
    cleared = response.headers["set-cookie"]
    assert cleared.startswith('studio_session="";') or cleared.startswith("studio_session=;")
    assert "Max-Age=0" in cleared
    assert (await owner.client.get("/api/auth/me")).status_code == 401
    # A copy of the cookie kept elsewhere no longer works either.
    replay = await new_client()
    replay.cookies.set("studio_session", token)
    assert (await replay.get("/api/auth/me")).status_code == 401
    assert (await replay.get(f"/api/organisations/{owner.organisation_id}")).status_code == 401


async def test_signing_out_without_a_session_succeeds(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/auth/sign-out")).status_code == 204


async def test_the_current_member_needs_a_valid_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).json() == {"detail": "Not signed in"}
    client.cookies.set("studio_session", "made-up-token")
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not signed in"}


async def test_each_member_sees_only_their_own_organisations(
    tenant_factory: TenantFactory,
) -> None:
    ada, grace = await tenant_factory(), await tenant_factory()

    ada_me = (await ada.client.get("/api/auth/me")).json()
    grace_me = (await grace.client.get("/api/auth/me")).json()

    assert [o["id"] for o in ada_me["organisations"]] == [ada.organisation_id]
    assert [o["id"] for o in grace_me["organisations"]] == [grace.organisation_id]
