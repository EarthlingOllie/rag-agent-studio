"""The mailer port's adapters, chosen by settings.

The SMTP adapter is exercised through the API against a local SMTP sink (aiosmtpd), standing
in for Mailpit. SES can't be reached from tests, so its adapter is checked against botocore's
Stubber, which validates the request against the SES API model.
"""

import email
import email.policy
import re
import socket
from collections.abc import AsyncIterator, Iterator
from email.message import EmailMessage

import boto3
import httpx
import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session
from asgi_lifespan import LifespanManager
from botocore.stub import Stubber
from fastapi import FastAPI

from app.mail.outbox import OutboxMailer
from app.mail.port import Email
from app.mail.ses import SesMailer
from app.mail.smtp import SmtpMailer
from app.main import create_app
from tests.conftest import BASE_URL, STUDIO_URL, SignedUpMember


class Sink:
    """Collects every message the SMTP server accepts."""

    def __init__(self) -> None:
        self.messages: list[tuple[Envelope, EmailMessage]] = []

    async def handle_DATA(self, server: object, session: Session, envelope: Envelope) -> str:  # noqa: N802
        content = envelope.content
        assert isinstance(content, bytes)
        parsed = email.message_from_bytes(content, policy=email.policy.default)
        assert isinstance(parsed, EmailMessage)
        self.messages.append((envelope, parsed))
        return "250 Message accepted"


@pytest.fixture
def smtp_sink() -> Iterator[tuple[Sink, int]]:
    sink = Sink()
    with socket.socket() as probe:  # a free port; aiosmtpd can't bind port 0 itself
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    controller = Controller(sink, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        yield sink, port
    finally:
        controller.stop()


@pytest.fixture
async def smtp_app(
    settings_env: pytest.MonkeyPatch, database_schema: None, smtp_sink: tuple[Sink, int]
) -> AsyncIterator[FastAPI]:
    _, port = smtp_sink
    settings_env.setenv("MAILER", "smtp")
    settings_env.setenv("SMTP_HOST", "127.0.0.1")
    settings_env.setenv("SMTP_PORT", str(port))
    settings_env.setenv("MAIL_FROM", "Studio <studio@example.test>")
    application = create_app()
    async with LifespanManager(application):
        yield application


async def test_the_smtp_mailer_delivers_reset_emails_when_settings_choose_it(
    smtp_app: FastAPI, smtp_sink: tuple[Sink, int]
) -> None:
    sink, _ = smtp_sink
    transport = httpx.ASGITransport(app=smtp_app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        signed_up = await client.post(
            "/api/auth/sign-up",
            json={
                "name": "Grace Hopper",
                "email": f"grace-{id(sink)}@example.test",
                "password": "a long enough password",
                "organisation_name": "Compilers",
            },
        )
        address = signed_up.json()["member"]["email"]
        await client.post("/api/auth/password-reset", json={"email": address})

    ((envelope, message),) = sink.messages
    assert envelope.rcpt_tos == [address]
    assert message["From"] == "Studio <studio@example.test>"
    assert message["To"] == address
    assert message["Subject"] == "Reset your RAG Agent Studio password"
    body = message.get_content()
    assert "Hello Grace Hopper," in body
    assert re.search(re.escape(STUDIO_URL) + r"/reset-password\?token=[\w-]{43}", body)


async def test_the_smtp_mailer_raises_when_the_server_is_unreachable() -> None:
    mailer = SmtpMailer(host="127.0.0.1", port=1, sender="s@example.test", timeout_seconds=1)

    with pytest.raises(OSError, match="refused"):
        await mailer.send(Email(to="a@example.test", subject="Hi", text="Hello"))


async def test_the_ses_mailer_sends_a_plain_text_email() -> None:
    client = boto3.client(
        "sesv2",
        region_name="eu-west-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
    )
    mailer = SesMailer(client, sender="Studio <studio@example.test>")
    with Stubber(client) as stubber:
        stubber.add_response(
            "send_email",
            {"MessageId": "0001"},
            {
                "FromEmailAddress": "Studio <studio@example.test>",
                "Destination": {"ToAddresses": ["ada@example.test"]},
                "Content": {
                    "Simple": {
                        "Subject": {"Data": "Hello", "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": "Hi Ada", "Charset": "UTF-8"}},
                    }
                },
            },
        )

        await mailer.send(Email(to="ada@example.test", subject="Hello", text="Hi Ada"))

        stubber.assert_no_pending_responses()


@pytest.mark.parametrize(
    ("setting", "adapter"),
    [("outbox", OutboxMailer), ("smtp", SmtpMailer), ("ses", SesMailer)],
)
async def test_settings_choose_the_mailer(
    settings_env: pytest.MonkeyPatch, database_schema: None, setting: str, adapter: type
) -> None:
    settings_env.setenv("MAILER", setting)
    settings_env.setenv("SES_REGION", "eu-west-2")
    application = create_app()
    async with LifespanManager(application):
        assert isinstance(application.state.mailer, adapter)


async def test_an_unknown_mailer_setting_fails_startup(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("MAILER", "carrier-pigeon")

    with pytest.raises(Exception, match="MAILER"):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_reset_emails_land_in_the_outbox_in_tests(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await client.post("/api/auth/password-reset", json={"email": owner.email})

    assert [message.to for message in outbox.sent] == [owner.email]
