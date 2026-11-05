"""Plain SMTP delivery, used with Mailpit in ``docker compose``."""

import asyncio
import smtplib
from email.message import EmailMessage

from app.mail.port import Email


def to_mime(email: Email, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    return message


class SmtpMailer:
    def __init__(self, *, host: str, port: int, sender: str, timeout_seconds: float) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._timeout_seconds = timeout_seconds

    def _send_blocking(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as connection:
            connection.send_message(message)

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(self._send_blocking, to_mime(email, self._sender))
