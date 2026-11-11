"""API seam: the signed-in Member edits their name and changes their password."""

import httpx

from tests.conftest import ClientFactory, SignedUpMember

NEW_PASSWORD = "a brand new password 123"


async def change_password(
    client: httpx.AsyncClient, current: str, new: str = NEW_PASSWORD
) -> httpx.Response:
    return await client.post(
        "/api/auth/me/password", json={"current_password": current, "new_password": new}
    )


async def sign_in(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/sign-in", json={"email": email, "password": password})


async def test_a_member_edits_their_name(owner: SignedUpMember) -> None:
    response = await owner.client.patch("/api/auth/me", json={"name": "  Ada King  "})

    assert response.status_code == 200
    assert response.json()["member"] == {
        "id": owner.member_id,
        "name": "Ada King",
        "email": owner.email,
        "mfa_enabled": False,
    }
    assert response.json()["organisations"][0]["id"] == owner.organisation_id
    me = await owner.client.get("/api/auth/me")
    assert me.json()["member"]["name"] == "Ada King"


async def test_a_name_must_not_be_blank(owner: SignedUpMember) -> None:
    response = await owner.client.patch("/api/auth/me", json={"name": "   "})

    assert response.status_code == 422
    me = await owner.client.get("/api/auth/me")
    assert me.json()["member"]["name"] == owner.name


async def test_editing_the_profile_needs_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.patch("/api/auth/me", json={"name": "Ada"})).status_code == 401
    assert (await change_password(client, "anything at all")).status_code == 401


async def test_a_member_changes_their_password_with_their_current_one(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    response = await change_password(owner.client, owner.password)

    assert response.status_code == 204
    assert (await sign_in(client, owner.email, owner.password)).status_code == 401
    assert (await sign_in(client, owner.email, NEW_PASSWORD)).status_code == 200


async def test_a_wrong_current_password_changes_nothing(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    response = await change_password(owner.client, "not my password at all")

    assert response.status_code == 400
    assert response.json() == {"detail": "Current password is incorrect"}
    assert (await owner.client.get("/api/auth/me")).status_code == 200
    assert (await sign_in(client, owner.email, owner.password)).status_code == 200


async def test_a_new_password_needs_at_least_twelve_characters(owner: SignedUpMember) -> None:
    response = await change_password(owner.client, owner.password, "short")

    assert response.status_code == 422


async def test_changing_the_password_ends_other_sessions_and_rotates_this_one(
    owner: SignedUpMember, new_client: ClientFactory
) -> None:
    phone = await new_client()
    assert (await sign_in(phone, owner.email, owner.password)).status_code == 200
    old_token = owner.client.cookies["studio_session"]

    response = await change_password(owner.client, owner.password)

    assert response.status_code == 204
    assert (await phone.get("/api/auth/me")).status_code == 401
    new_token = owner.client.cookies["studio_session"]
    assert new_token != old_token
    assert (await owner.client.get("/api/auth/me")).status_code == 200
    replay = await new_client()
    replay.cookies.set("studio_session", old_token)
    assert (await replay.get("/api/auth/me")).status_code == 401
