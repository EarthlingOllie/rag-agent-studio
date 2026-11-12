"""API seam: forgotten-password reset by emailed link."""

import hashlib
import logging
import re
import uuid
from contextlib import AsyncExitStack
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.mail.outbox import OutboxMailer
from app.mail.port import Email
from tests.conftest import (
    BASE_URL,
    STUDIO_URL,
    TEST_DATABASE_URL,
    ClientFactory,
    SignedUpMember,
)
from tests.fakes.clock import ControllableClock

NEW_PASSWORD = "a brand new password 123"
RESET_ACCEPTED = {"detail": "If that email is registered, a reset link is on its way."}
INVALID_LINK = {"detail": "This reset link is invalid or has expired."}


def reset_token(outbox: OutboxMailer, email: str) -> str:
    """The token from the last reset email sent to ``email``."""
    (message,) = [m for m in outbox.sent if m.to == email][-1:]
    match = re.search(re.escape(STUDIO_URL) + r"/reset-password\?token=([\w-]+)", message.text)
    assert match is not None, message.text
    return match.group(1)


async def request_reset(client: httpx.AsyncClient, email: str) -> httpx.Response:
    return await client.post("/api/auth/password-reset", json={"email": email})


async def complete_reset(
    client: httpx.AsyncClient, token: str, password: str = NEW_PASSWORD
) -> httpx.Response:
    return await client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": password}
    )


async def sign_in(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/sign-in", json={"email": email, "password": password})


async def test_a_member_resets_a_forgotten_password_by_emailed_link(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    response = await request_reset(client, owner.email.upper())

    assert response.status_code == 202
    assert response.json() == RESET_ACCEPTED
    (message,) = outbox.sent
    assert message.to == owner.email
    assert message.subject == "Reset your RAG Agent Studio password"
    assert owner.name in message.text
    token = reset_token(outbox, owner.email)

    completed = await complete_reset(client, token)

    assert completed.status_code == 204
    assert (await sign_in(client, owner.email, owner.password)).status_code == 401
    assert (await sign_in(client, owner.email, NEW_PASSWORD)).status_code == 200


async def test_requesting_a_reset_answers_the_same_whether_or_not_the_email_is_registered(
    owner: SignedUpMember, new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    responses = [
        await request_reset(await new_client(), email)
        for email in (owner.email, f"nobody-{owner.email}")
    ]

    observed = {
        (
            response.status_code,
            response.content,
            tuple(sorted((k, v) for k, v in response.headers.items() if k != "date")),
        )
        for response in responses
    }
    assert len(observed) == 1
    (status, content, _) = observed.pop()
    assert status == 202
    assert httpx.Response(status, content=content).json() == RESET_ACCEPTED
    assert [message.to for message in outbox.sent] == [owner.email]


async def test_a_reset_link_works_only_once(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await request_reset(client, owner.email)
    token = reset_token(outbox, owner.email)
    assert (await complete_reset(client, token)).status_code == 204

    again = await complete_reset(client, token, "yet another password 456")

    assert again.status_code == 400
    assert again.json() == INVALID_LINK
    assert (await sign_in(client, owner.email, NEW_PASSWORD)).status_code == 200


async def test_a_reset_link_expires_after_an_hour(
    owner: SignedUpMember,
    client: httpx.AsyncClient,
    outbox: OutboxMailer,
    clock: ControllableClock,
) -> None:
    await request_reset(client, owner.email)
    expiring = reset_token(outbox, owner.email)
    assert "expires in 60 minutes" in outbox.sent[-1].text

    clock.advance(timedelta(minutes=60))
    expired = await complete_reset(client, expiring)

    assert expired.status_code == 400
    assert expired.json() == INVALID_LINK
    await request_reset(client, owner.email)
    fresh = reset_token(outbox, owner.email)
    clock.advance(timedelta(minutes=59))
    assert (await complete_reset(client, fresh)).status_code == 204


async def test_completing_a_reset_uses_up_the_members_other_reset_links(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await request_reset(client, owner.email)
    first = reset_token(outbox, owner.email)
    await request_reset(client, owner.email)
    second = reset_token(outbox, owner.email)

    assert (await complete_reset(client, second)).status_code == 204

    assert (await complete_reset(client, first, "yet another password 456")).status_code == 400


async def test_an_unknown_reset_token_is_refused(client: httpx.AsyncClient) -> None:
    response = await complete_reset(client, "not-a-real-token")

    assert response.status_code == 400
    assert response.json() == INVALID_LINK


async def test_a_reset_needs_a_password_of_at_least_twelve_characters(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await request_reset(client, owner.email)
    token = reset_token(outbox, owner.email)

    too_short = await complete_reset(client, token, "short")

    assert too_short.status_code == 422
    assert (await complete_reset(client, token)).status_code == 204


async def test_reset_tokens_are_stored_only_as_hashes(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await request_reset(client, owner.email)
    token = reset_token(outbox, owner.email)

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            stored = (
                await connection.execute(
                    text(
                        "SELECT t.token_hash FROM password_reset_tokens t"
                        " JOIN members m ON m.id = t.member_id WHERE m.email = :email"
                    ),
                    {"email": owner.email},
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored


async def test_completing_a_reset_signs_the_member_out_everywhere(
    owner: SignedUpMember, new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    laptop = await new_client()
    assert (await sign_in(laptop, owner.email, owner.password)).status_code == 200
    visitor = await new_client()
    await request_reset(visitor, owner.email)

    assert (await complete_reset(visitor, reset_token(outbox, owner.email))).status_code == 204

    assert (await owner.client.get("/api/auth/me")).status_code == 401
    assert (await laptop.get("/api/auth/me")).status_code == 401
    assert (await sign_in(visitor, owner.email, NEW_PASSWORD)).status_code == 200


class BrokenMailer:
    async def send(self, email: Email) -> None:
        raise ConnectionRefusedError("the mail server is down")


async def test_a_failed_reset_email_is_logged_and_the_answer_is_unchanged(
    app: FastAPI,
    owner: SignedUpMember,
    client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app.state.mailer = BrokenMailer()

    with caplog.at_level(logging.ERROR, logger="app.auth.account_api"):
        response = await request_reset(client, owner.email)

    assert response.status_code == 202
    assert response.json() == RESET_ACCEPTED
    assert [r.getMessage() for r in caplog.records] == ["Sending a password reset email failed"]


async def test_changing_the_password_uses_up_outstanding_reset_links(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await request_reset(client, owner.email)
    token = reset_token(outbox, owner.email)
    changed = await owner.client.post(
        "/api/auth/me/password",
        json={"current_password": owner.password, "new_password": "changed on purpose 789"},
    )
    assert changed.status_code == 204

    assert (await complete_reset(client, token)).status_code == 400


# AUTH-R2-F2: reset requests are limited per email and per IP address. Over the limit the
# answer is the same 202 and nothing is sent, so the limit reveals nothing about the email.
RESETS_PER_EMAIL = 3
RESETS_PER_IP = 20


async def _client_from(app: FastAPI, ip: str, stack: AsyncExitStack) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 50000))
    return await stack.enter_async_context(
        httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    )


def _unique_ip() -> str:
    return f"203.0.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 254 + 1}"


async def test_reset_emails_to_one_address_are_limited_per_hour(
    app: FastAPI, owner: SignedUpMember, outbox: OutboxMailer, clock: ControllableClock
) -> None:
    async with AsyncExitStack() as stack:
        answers = []
        for _ in range(RESETS_PER_EMAIL + 1):
            # From a new address each time, so only the per-email limit applies.
            client = await _client_from(app, _unique_ip(), stack)
            answers.append(await request_reset(client, owner.email))
            clock.advance(60)

        assert [(a.status_code, a.json()) for a in answers] == [(202, RESET_ACCEPTED)] * (
            RESETS_PER_EMAIL + 1
        )
        assert [m.to for m in outbox.sent] == [owner.email] * RESETS_PER_EMAIL

        clock.advance(timedelta(hours=1))
        client = await _client_from(app, _unique_ip(), stack)
        assert (await request_reset(client, owner.email)).status_code == 202
        assert len(outbox.sent) == RESETS_PER_EMAIL + 1


async def test_reset_requests_from_one_ip_are_limited_across_emails(
    app: FastAPI, owner: SignedUpMember, outbox: OutboxMailer, clock: ControllableClock
) -> None:
    async with AsyncExitStack() as stack:
        attacker = await _client_from(app, _unique_ip(), stack)
        for i in range(RESETS_PER_IP):
            assert (await request_reset(attacker, f"nobody-{i}-{owner.email}")).status_code == 202

        throttled = await request_reset(attacker, owner.email)

        assert throttled.status_code == 202
        assert throttled.json() == RESET_ACCEPTED
        assert outbox.sent == []
        elsewhere = await _client_from(app, _unique_ip(), stack)
        assert (await request_reset(elsewhere, owner.email)).status_code == 202
        assert [m.to for m in outbox.sent] == [owner.email]


async def test_a_new_reset_link_supersedes_the_earlier_ones(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await request_reset(client, owner.email)
    earlier = reset_token(outbox, owner.email)
    await request_reset(client, owner.email)
    latest = reset_token(outbox, owner.email)

    superseded = await complete_reset(client, earlier)

    assert superseded.status_code == 400
    assert superseded.json() == INVALID_LINK
    assert (await complete_reset(client, latest)).status_code == 204
