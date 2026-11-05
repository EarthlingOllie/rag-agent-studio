"""The in-memory mailer tests read sent emails from."""

from app.mail.port import Email


class OutboxMailer:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)
