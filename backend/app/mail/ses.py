"""AWS SES (v2) delivery. Built now; switched on when a sending domain exists."""

import asyncio
from typing import TYPE_CHECKING

from app.mail.port import Email

if TYPE_CHECKING:
    from mypy_boto3_sesv2 import SESV2Client


class SesMailer:
    def __init__(self, client: "SESV2Client", *, sender: str) -> None:
        self._client = client
        self._sender = sender

    def _send_blocking(self, email: Email) -> None:
        self._client.send_email(
            FromEmailAddress=self._sender,
            Destination={"ToAddresses": [email.to]},
            Content={
                "Simple": {
                    "Subject": {"Data": email.subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": email.text, "Charset": "UTF-8"}},
                }
            },
        )

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(self._send_blocking, email)
