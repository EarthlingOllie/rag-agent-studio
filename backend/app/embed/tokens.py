"""The widget's two tokens, both signed with HMAC-SHA256 so a tampered one is refused before
anything is looked up.

- The **bootstrap token** is short-lived and bound to an Agent's public ID. The shell hands it to
  the widget, which exchanges it for a Conversation token. It is stateless.
- The **Conversation token** is opaque, bound to one Visitor Conversation (and through it to the
  Agent), and carries a random nonce. Only its SHA-256 hash is stored, on the Conversation, so a
  copy of the database can't be replayed. It expires 24 hours after the Conversation's last
  activity, sliding; the service checks that against the stored Conversation.

The signing key is derived from the deployment's key wrapper key, with its own label, so no
other secret has to be provisioned.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

BOOTSTRAP_TTL = timedelta(minutes=15)
# How far ahead of this process's clock a bootstrap token's issue time may be: the API's tasks'
# clocks may differ a little. A token dated further ahead is forged, and would otherwise never
# expire.
BOOTSTRAP_CLOCK_SKEW = timedelta(minutes=1)
CONVERSATION_IDLE_TTL = timedelta(hours=24)

_BOOTSTRAP = "wb1"
_CONVERSATION = "wc1"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class TokenSigner:
    def __init__(self, secret: str) -> None:
        self._key = hmac.new(b"rag-agent-studio widget tokens", secret.encode(), "sha256").digest()

    def _sign(self, *parts: str) -> str:
        payload = ".".join(parts)
        return payload + "." + _b64(hmac.new(self._key, payload.encode(), "sha256").digest())

    def _verify(self, token: str, kind: str, count: int) -> list[str] | None:
        parts = token.split(".")
        if len(parts) != count + 2 or parts[0] != kind:
            return None
        expected = self._sign(*parts[:-1])
        if not hmac.compare_digest(expected.encode(), token.encode()):
            return None
        return parts[1:-1]

    def bootstrap(self, public_id: str, *, now: datetime) -> str:
        return self._sign(_BOOTSTRAP, public_id, str(int(now.timestamp())))

    def bootstrap_agent(self, token: str, *, now: datetime) -> str | None:
        """The public ID of the Agent the bootstrap token was issued for, or None when it is
        tampered with or has expired."""
        parts = self._verify(token, _BOOTSTRAP, 2)
        if parts is None or not parts[1].isdigit():
            return None
        public_id, issued = parts
        age = now.timestamp() - int(issued)
        if not -BOOTSTRAP_CLOCK_SKEW.total_seconds() <= age <= BOOTSTRAP_TTL.total_seconds():
            return None
        return public_id

    def conversation(self, conversation_id: uuid.UUID) -> str:
        return self._sign(_CONVERSATION, conversation_id.hex, secrets.token_urlsafe(24))

    def conversation_id(self, token: str) -> uuid.UUID | None:
        """The Conversation a correctly signed Conversation token names; the caller still checks
        its hash and expiry against the stored Conversation."""
        parts = self._verify(token, _CONVERSATION, 2)
        if parts is None:
            return None
        return uuid.UUID(hex=parts[0])


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expired(last_activity_at: datetime, *, now: datetime) -> bool:
    return now - last_activity_at > CONVERSATION_IDLE_TTL
