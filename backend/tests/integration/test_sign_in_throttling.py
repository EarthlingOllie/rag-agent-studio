"""Sign-in rate limiting and lockout at the API seam.

Repeated failures are counted per account and per IP address. After a few free failures each
attempt must wait progressively longer; after more, sign-in is locked out for a while.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import BASE_URL, SignedUpMember
from tests.fakes.clock import ControllableClock

LOCKOUT_SECONDS = 120
IP_DELAY_AFTER = 8
IP_LOCKOUT_AFTER = 12


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A configured lockout length, so the tests show the setting is honoured.

    The IP limits are lowered from their defaults (20 and 100) to keep the tests short; the
    account limits keep their defaults: three free failures, a lockout after ten.
    """
    settings_env.setenv("SIGN_IN_LOCKOUT_SECONDS", str(LOCKOUT_SECONDS))
    settings_env.setenv("SIGN_IN_IP_DELAY_AFTER_FAILURES", str(IP_DELAY_AFTER))
    settings_env.setenv("SIGN_IN_IP_LOCKOUT_AFTER_FAILURES", str(IP_LOCKOUT_AFTER))
    # The load balancers, whose X-Forwarded-For is believed (spec 06: trusted-proxy configuration).
    settings_env.setenv("TRUSTED_PROXIES", "10.0.0.0/16")
    return settings_env


IpClientFactory = Callable[[str], Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def client_from(app: FastAPI) -> AsyncIterator[IpClientFactory]:
    """Opens a client whose requests come from the given IP address."""
    async with AsyncExitStack() as stack:

        async def open_client(ip: str) -> httpx.AsyncClient:
            transport = httpx.ASGITransport(app=app, client=(ip, 50000))
            return await stack.enter_async_context(
                httpx.AsyncClient(transport=transport, base_url=BASE_URL)
            )

        yield open_client


def _unique_ip() -> str:
    """A documentation-range address no other test uses."""
    return f"198.51.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 254 + 1}"


async def _sign_in(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/sign-in", json={"email": email, "password": password})


async def _fail_until_locked(
    client: httpx.AsyncClient, clock: ControllableClock, email: str
) -> list[httpx.Response]:
    """Fails sign-in, waiting out each delay, until the account is locked; returns every answer."""
    responses = []
    for _ in range(100):
        response = await _sign_in(client, email, "wrong password")
        responses.append(response)
        if response.status_code == 429:
            if response.json()["locked"]:
                return responses
            clock.advance(response.json()["retry_after_seconds"])
    raise AssertionError("sign-in never locked")


async def test_repeated_failures_lock_the_account_even_for_the_right_password(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    client = await client_from(_unique_ip())

    responses = await _fail_until_locked(client, clock, owner.email)
    locked = await _sign_in(client, owner.email, owner.password)

    assert [r.status_code for r in responses].count(401) == 10
    assert locked.status_code == 429
    assert locked.json() == {
        "detail": "Too many failed sign-in attempts",
        "locked": True,
        "retry_after_seconds": LOCKOUT_SECONDS,
    }
    assert locked.headers["retry-after"] == str(LOCKOUT_SECONDS)
    assert "set-cookie" not in locked.headers


async def test_after_three_free_failures_each_attempt_waits_progressively_longer(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    client = await client_from(_unique_ip())

    responses = await _fail_until_locked(client, clock, owner.email)

    statuses = [r.status_code for r in responses]
    assert statuses[:3] == [401, 401, 401]
    delays = [r.json() for r in responses if r.status_code == 429]
    assert [d["retry_after_seconds"] for d in delays] == [1, 2, 4, 8, 16, 30, 30, LOCKOUT_SECONDS]
    assert [d["locked"] for d in delays] == [False] * 7 + [True]
    assert all(d["detail"] == "Too many failed sign-in attempts" for d in delays)
    delayed = next(r for r in responses if r.status_code == 429)
    assert delayed.headers["retry-after"] == "1"


async def test_a_delay_refuses_even_the_right_password_until_it_has_passed(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    client = await client_from(_unique_ip())
    for _ in range(4):
        await _sign_in(client, owner.email, "wrong password")
        clock.advance(1)
    # Four failures: the next attempt must wait two seconds after the last one.
    clock.advance(0.5)

    early = await _sign_in(client, owner.email, owner.password)
    clock.advance(0.5)
    on_time = await _sign_in(client, owner.email, owner.password)

    assert early.status_code == 429
    assert early.json()["retry_after_seconds"] == 1
    assert on_time.status_code == 200
    assert "studio_session" in on_time.cookies


async def test_the_lockout_expires_after_the_configured_time(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    client = await client_from(_unique_ip())
    await _fail_until_locked(client, clock, owner.email)

    clock.advance(LOCKOUT_SECONDS - 30)
    # Attempts refused during the lockout don't count, so they can't extend it.
    still_locked = await _sign_in(client, owner.email, owner.password)
    clock.advance(29)
    last_second = await _sign_in(client, owner.email, owner.password)
    clock.advance(1)
    after = await _sign_in(client, owner.email, owner.password)

    assert still_locked.status_code == 429
    assert still_locked.json() == {
        "detail": "Too many failed sign-in attempts",
        "locked": True,
        "retry_after_seconds": 30,
    }
    assert last_second.status_code == 429
    assert last_second.json()["retry_after_seconds"] == 1
    assert after.status_code == 200


async def test_a_successful_sign_in_clears_the_account_failures(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    client = await client_from(_unique_ip())
    for _ in range(3):
        await _sign_in(client, owner.email, "wrong password")
    clock.advance(1)
    assert (await _sign_in(client, owner.email, owner.password)).status_code == 200

    again = [await _sign_in(client, owner.email, "wrong password") for _ in range(3)]

    assert [r.status_code for r in again] == [401, 401, 401]


async def test_failures_are_forgotten_once_the_lockout_time_passes_without_another(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    client = await client_from(_unique_ip())
    for _ in range(3):
        await _sign_in(client, owner.email, "wrong password")
    clock.advance(LOCKOUT_SECONDS)

    again = [await _sign_in(client, owner.email, "wrong password") for _ in range(3)]

    assert [r.status_code for r in again] == [401, 401, 401]


def _unknown_email() -> str:
    return f"nobody-{uuid.uuid4().hex[:12]}@example.test"


async def test_many_failures_from_one_ip_lock_that_ip_out_for_every_account(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    ip = _unique_ip()
    attacker = await client_from(ip)
    statuses: list[int] = []
    for _ in range(100):
        if len(statuses) == IP_LOCKOUT_AFTER:
            break
        response = await _sign_in(attacker, _unknown_email(), "guessed password")
        if response.status_code == 429:
            clock.advance(response.json()["retry_after_seconds"])
        else:
            statuses.append(response.status_code)

    from_that_ip = await _sign_in(await client_from(ip), owner.email, owner.password)
    from_elsewhere = await _sign_in(await client_from(_unique_ip()), owner.email, owner.password)

    assert statuses == [401] * IP_LOCKOUT_AFTER
    assert from_that_ip.status_code == 429
    assert from_that_ip.json()["locked"] is True
    assert from_that_ip.json()["retry_after_seconds"] == LOCKOUT_SECONDS
    assert from_elsewhere.status_code == 200


async def test_an_ip_waits_progressively_longer_after_its_free_failures(
    client_from: IpClientFactory, clock: ControllableClock
) -> None:
    attacker = await client_from(_unique_ip())
    for _ in range(IP_DELAY_AFTER):
        assert (await _sign_in(attacker, _unknown_email(), "guess")).status_code == 401

    delayed = await _sign_in(attacker, _unknown_email(), "guess")

    assert delayed.status_code == 429
    assert delayed.json() == {
        "detail": "Too many failed sign-in attempts",
        "locked": False,
        "retry_after_seconds": 1,
    }


async def _guess_as(client: httpx.AsyncClient, forwarded_for: str) -> int:
    """A failed sign-in carrying the given X-Forwarded-For; returns the status."""
    response = await client.post(
        "/api/auth/sign-in",
        json={"email": _unknown_email(), "password": "guess"},
        headers={"X-Forwarded-For": forwarded_for},
    )
    return response.status_code


async def test_failures_through_a_trusted_proxy_count_per_forwarded_address(
    client_from: IpClientFactory, clock: ControllableClock
) -> None:
    balancer = await client_from(f"10.0.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 254 + 1}")
    attacker = _unique_ip()
    # Whatever a client writes on the left is its own claim; the balancer saw the right-hand one.
    neighbour = f"{attacker}, {_unique_ip()}"
    for _ in range(IP_DELAY_AFTER):
        assert await _guess_as(balancer, attacker) == 401

    assert await _guess_as(balancer, attacker) == 429
    assert await _guess_as(balancer, neighbour) == 401


async def test_a_client_connecting_directly_cannot_pose_as_another_address(
    client_from: IpClientFactory, clock: ControllableClock
) -> None:
    attacker = await client_from(_unique_ip())
    for _ in range(IP_DELAY_AFTER):
        assert await _guess_as(attacker, _unique_ip()) == 401

    assert await _guess_as(attacker, _unique_ip()) == 429


def _observable(response: httpx.Response) -> tuple[int, bytes, tuple[tuple[str, str], ...]]:
    headers = tuple(sorted((k, v) for k, v in response.headers.items() if k != "date"))
    return response.status_code, response.content, headers


async def test_throttling_is_identical_for_an_unknown_email_and_a_wrong_password(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    """The same attempts at the same moments get byte-identical answers, delays and lockout."""
    attempts = {"registered email": owner.email, "unknown email": _unknown_email()}
    clients = {label: await client_from(_unique_ip()) for label in attempts}
    observed: dict[str, list[tuple[int, bytes, tuple[tuple[str, str], ...]]]] = {
        label: [] for label in attempts
    }

    for _ in range(30):
        for label, email in attempts.items():
            response = await _sign_in(clients[label], email, "wrong password")
            observed[label].append(_observable(response))
        clock.advance(4)

    assert observed["registered email"] == observed["unknown email"]
    answers = [httpx.Response(s, content=c).json() for s, c, _ in observed["registered email"]]
    assert {"detail": "Email or password is incorrect"} in answers
    assert any(a.get("locked") is False for a in answers)
    assert answers[-1]["locked"] is True


async def _lockout_events(owner: SignedUpMember) -> list[dict[str, object]]:
    """The lockouts in the Owner's Audit tab, through the Owner-only list endpoint."""
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "member.locked_out"},
    )
    assert response.status_code == 200, response.text
    return [{k: v for k, v in event.items() if k != "id"} for event in response.json()["items"]]


async def test_an_account_lockout_is_recorded_as_an_audit_event(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    ip = _unique_ip()
    client = await client_from(ip)
    for _ in range(9):
        await _sign_in(client, owner.email, "wrong password")
        clock.advance(60)
    assert await _lockout_events(owner) == []  # delays alone aren't audited

    await _sign_in(client, owner.email, "wrong password")
    await _sign_in(client, owner.email, owner.password)  # refused while locked: no new event

    assert await _lockout_events(owner) == [
        {
            "occurred_at": "2026-11-05T09:09:00Z",
            "actor": None,
            "action": "member.locked_out",
            "target": {"type": "member", "id": owner.member_id},
            "before": None,
            "after": {
                "scope": "account",
                "ip": ip,
                "failures": 10,
                "locked_until": "2026-11-05T09:11:00+00:00",
            },
        }
    ]


async def test_an_ip_lockout_is_recorded_for_the_member_whose_sign_in_tripped_it(
    owner: SignedUpMember, client_from: IpClientFactory, clock: ControllableClock
) -> None:
    ip = _unique_ip()
    attacker = await client_from(ip)
    for _ in range(IP_LOCKOUT_AFTER - 1):
        await _sign_in(attacker, _unknown_email(), "guess")
        clock.advance(60)

    await _sign_in(attacker, owner.email, "guess")

    (event,) = await _lockout_events(owner)
    assert event["target"] == {"type": "member", "id": owner.member_id}
    assert event["after"] == {
        "scope": "ip",
        "ip": ip,
        "failures": IP_LOCKOUT_AFTER,
        "locked_until": "2026-11-05T09:13:00+00:00",
    }
