"""API seam: cross-site request forgery (AUTH-R2-F1). The Studio session cookie is SameSite=Lax,
which still sends it on requests from a sibling subdomain (same-site), and a bodyless POST needs
no preflight. So every state-changing ``/api/`` request from a browser must come from the Studio
itself: ``Sec-Fetch-Site`` (when the browser sends it) must be ``same-origin``, and an ``Origin``
(when sent) must be the Studio's. Clients that send neither (scripts, the tests) are not
browsers, so a forged request can't come from them. The widget's routes (token-authenticated,
cross-origin by design) and the demo pages' routes are exempt."""

import httpx
import pytest

from tests.conftest import STUDIO_URL, SignedUpMember

REFUSED = {"detail": "Cross-site request refused."}


@pytest.mark.parametrize(
    "headers",
    [
        # A page on a sibling subdomain: SameSite=Lax still sends the cookie.
        {"Sec-Fetch-Site": "same-site", "Origin": "https://evil.example.test"},
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example.test"},
        # The browser's own verdict wins even when the Origin looks right.
        {"Sec-Fetch-Site": "same-site", "Origin": STUDIO_URL},
        # An older browser without Fetch Metadata: the Origin decides.
        {"Origin": "https://evil.example.test"},
        {"Origin": "null"},
    ],
)
async def test_a_forged_bodyless_post_does_not_sign_the_member_out(
    owner: SignedUpMember, headers: dict[str, str]
) -> None:
    response = await owner.client.post("/api/auth/sign-out", headers=headers)

    assert response.status_code == 403
    assert response.json() == REFUSED
    assert (await owner.client.get("/api/auth/me")).status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/api/auth/me/active-organisation"),
        ("PATCH", "/api/auth/me"),
        ("DELETE", "/api/organisations/{organisation_id}/members/{member_id}"),
        # AUTH-I1: a forged request must not start MFA enrolment.
        ("POST", "/api/auth/mfa/enrolment"),
    ],
)
async def test_every_state_changing_method_is_checked(
    owner: SignedUpMember, method: str, path: str
) -> None:
    response = await owner.client.request(
        method,
        path.format(organisation_id=owner.organisation_id, member_id=owner.member_id),
        json={},
        headers={"Sec-Fetch-Site": "same-site"},
    )

    assert response.status_code == 403
    assert response.json() == REFUSED


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "same-origin", "Origin": STUDIO_URL},
        {"Origin": STUDIO_URL},
        {"Sec-Fetch-Site": "same-origin"},
        {},
    ],
)
async def test_the_studios_own_requests_are_let_through(
    owner: SignedUpMember, headers: dict[str, str]
) -> None:
    response = await owner.client.post("/api/auth/sign-out", headers=headers)

    assert response.status_code == 204


async def test_reads_are_not_checked(owner: SignedUpMember) -> None:
    response = await owner.client.get(
        "/api/auth/me",
        headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example.test"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/widget/agents/unknown-agent/conversations",
        "/api/demo/attacks/benign-control",
    ],
)
async def test_the_widget_and_demo_routes_are_exempt(client: httpx.AsyncClient, path: str) -> None:
    response = await client.post(
        path,
        json={"bootstrap_token": "not-a-token"},
        headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://shop.example.test"},
    )

    assert response.json() != REFUSED


async def test_routes_outside_the_api_are_not_checked(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/widget/a/unknown-agent", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.json() != REFUSED
