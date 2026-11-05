"""What every mailer adapter implements, and the email it sends."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Email:
    """A rendered email, ready to send. Plain text only, so every client shows it the same."""

    to: str
    subject: str
    text: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None:
        """Delivers the email, or raises if the transport refuses it."""
        ...
