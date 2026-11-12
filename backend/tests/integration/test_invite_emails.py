"""API seam: invite emails can't be turned into a spam or phishing channel (TEN-F3).

Two things are observed through the API and the outbox: invite emails are rate limited per
Owner and per Organisation (a refused send still gives the Owner a working link, it just
isn't emailed), and the names an Owner controls reach the email only as short, single-line
text with links taken out.
"""

import uuid
from datetime import timedelta

import httpx

from app.mail.outbox import OutboxMailer
from tests.conftest import (
    ClientFactory,
    MemberFactory,
    SignedUpMember,
    new_member_details,
)
from tests.fakes.clock import ControllableClock

PER_OWNER_PER_HOUR = 20
PER_ORGANISATION_PER_HOUR = 50
HOUR = timedelta(hours=1)


def invites_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/invites"


def unique_email() -> str:
    return f"invited-{uuid.uuid4().hex[:12]}@example.test"


async def invite(owner: SignedUpMember, *, send_email: bool = True) -> httpx.Response:
    response = await owner.client.post(
        invites_path(owner.organisation_id),
        json={"email": unique_email(), "role": "editor", "send_email": send_email},
    )
    assert response.status_code == 201, response.text
    return response


async def look_up(client: httpx.AsyncClient, link: str) -> httpx.Response:
    token = link.rsplit("token=", 1)[1]
    return await client.post("/api/invites/lookup", json={"token": token})


# Throttling


async def test_an_owner_can_email_only_so_many_invites_an_hour(
    owner: SignedUpMember,
    client: httpx.AsyncClient,
    clock: ControllableClock,
    outbox: OutboxMailer,
) -> None:
    sent = [(await invite(owner)).json()["email_sent"] for _ in range(PER_OWNER_PER_HOUR)]

    refused = (await invite(owner)).json()

    assert sent == [True] * PER_OWNER_PER_HOUR
    assert refused["email_sent"] is False
    assert len(outbox.sent) == PER_OWNER_PER_HOUR
    # The Invite exists all the same, and its link works.
    assert (await look_up(client, refused["link"])).status_code == 200
    # Copy-the-link invites send nothing, so they aren't limited.
    assert (await invite(owner, send_email=False)).status_code == 201

    clock.advance(HOUR - timedelta(seconds=1))
    assert (await invite(owner)).json()["email_sent"] is False
    clock.advance(timedelta(seconds=1))
    assert (await invite(owner)).json()["email_sent"] is True
    assert len(outbox.sent) == PER_OWNER_PER_HOUR + 1


async def test_renewing_with_an_email_counts_towards_the_limit(
    owner: SignedUpMember, outbox: OutboxMailer
) -> None:
    body = (await invite(owner, send_email=False)).json()
    renew = f"{invites_path(owner.organisation_id)}/{body['invite']['id']}/renew"

    renewed = [
        (await owner.client.post(renew, json={"send_email": True})).json()["email_sent"]
        for _ in range(PER_OWNER_PER_HOUR + 1)
    ]

    assert renewed == [True] * PER_OWNER_PER_HOUR + [False]
    assert len(outbox.sent) == PER_OWNER_PER_HOUR


async def test_an_organisation_can_email_only_so_many_invites_an_hour(
    owner: SignedUpMember, member_factory: MemberFactory, outbox: OutboxMailer
) -> None:
    second, third = await member_factory(owner, "owner"), await member_factory(owner, "owner")
    for sender in (owner, second):
        for _ in range(PER_OWNER_PER_HOUR):
            await invite(sender)
    for _ in range(PER_ORGANISATION_PER_HOUR - 2 * PER_OWNER_PER_HOUR):
        await invite(third)
    assert len(outbox.sent) == PER_ORGANISATION_PER_HOUR

    # The third Owner is under their own limit, but the Organisation's is used up.
    assert (await invite(third)).json()["email_sent"] is False
    assert len(outbox.sent) == PER_ORGANISATION_PER_HOUR


async def test_one_owners_limit_does_not_hold_back_another_organisation(
    owner: SignedUpMember, new_client: ClientFactory
) -> None:
    for _ in range(PER_OWNER_PER_HOUR):
        await invite(owner)
    other = await _sign_up(new_client)

    assert (await invite(other)).json()["email_sent"] is True
    assert (await invite(owner)).json()["email_sent"] is False


# The names in the email


async def _sign_up(new_client: ClientFactory, **details: str) -> SignedUpMember:
    signed_in = await new_client()
    fields = new_member_details(**details)
    response = await signed_in.post("/api/auth/sign-up", json=fields)
    assert response.status_code == 201, response.text
    body = response.json()
    (organisation,) = body["organisations"]
    return SignedUpMember(
        client=signed_in,
        member_id=body["member"]["id"],
        name=body["member"]["name"],
        email=fields["email"],
        password=fields["password"],
        organisation_id=organisation["id"],
        organisation_name=organisation["name"],
    )


async def test_owner_chosen_names_reach_the_email_without_links_or_extra_lines(
    new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    owner = await _sign_up(
        new_client,
        name="Mallory\n\nURGENT: confirm your password at https://evil.example/login",
        organisation_name="IT Helpdesk\r\nBcc: victim@example.test www.evil.example/reset",
    )

    await invite(owner)

    (message,) = outbox.sent
    assert message.subject == "Join IT Helpdesk Bcc: victim@example[.]test on RAG Agent Studio"
    assert message.text.startswith(
        "Hello,\n\nMallory URGENT: confirm your password at has invited you to join "
        "IT Helpdesk Bcc: victim@example[.]test on RAG Agent Studio as an Editor."
    )
    for forbidden in ("https://evil", "www.", "evil.example", "\r"):
        assert forbidden not in message.subject + message.text


async def test_long_names_are_cut_short_in_the_email(
    new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    owner = await _sign_up(new_client, name="N" * 200, organisation_name="O" * 200)

    await invite(owner)

    (message,) = outbox.sent
    assert message.subject == f"Join {'O' * 59}… on RAG Agent Studio"
    assert f"{'N' * 59}… has invited you to join {'O' * 59}…" in message.text


async def test_ordinary_names_reach_the_email_unchanged(
    owner: SignedUpMember, outbox: OutboxMailer
) -> None:
    await invite(owner)

    (message,) = outbox.sent
    assert message.subject == f"Join {owner.organisation_name} on RAG Agent Studio"
    assert f"{owner.name} has invited you to join {owner.organisation_name} on" in message.text


async def test_a_name_that_is_only_a_link_is_left_out(
    new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    owner = await _sign_up(
        new_client, name="https://evil.example/a", organisation_name="www.evil.example"
    )

    await invite(owner)

    (message,) = outbox.sent
    assert message.subject == "Join an Organisation on RAG Agent Studio"
    assert "Someone has invited you to join an Organisation on RAG Agent Studio" in message.text
