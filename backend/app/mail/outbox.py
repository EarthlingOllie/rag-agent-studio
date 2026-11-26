"""The in-memory mailer tests read sent emails from.

Told to, it refuses the next send to an address (as a mail server that turned it down would),
and its kill switch stops the process at the send to an address (point ``send to <address>``)
as a process that died there would (``app.jobs.faults``)."""

from app.jobs.faults import KillSwitch
from app.mail.port import Email


class MailRefusedError(Exception):
    """The outbox refused the send, as a mail server can."""


class OutboxMailer:
    def __init__(self) -> None:
        self.sent: list[Email] = []
        self.kill_switch = KillSwitch()
        self._refusing: set[str] = set()

    def refuse(self, address: str) -> None:
        """The next send to ``address`` raises ``MailRefusedError``."""
        self._refusing.add(address)

    async def send(self, email: Email) -> None:
        self.kill_switch.check(f"send to {email.to}")
        if email.to in self._refusing:
            self._refusing.discard(email.to)
            raise MailRefusedError(email.to)
        self.sent.append(email)
