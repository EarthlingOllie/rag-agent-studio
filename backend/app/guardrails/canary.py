"""The Canary token: a per-request secret placed in the platform preamble.

The model is told never to reveal it, so seeing it in a reply means the prompt is leaking.

- ``CanaryFilter`` wraps the answer's token stream. It holds back a buffer as long as the
  canary (counted in non-whitespace characters) and releases text only once that text can no
  longer be the start of a canary straddling chunk boundaries. The comparison ignores
  whitespace and case, so ``3F9A 1C7E…`` or a canary broken over lines is caught too. When the
  canary appears, the filter says so and releases nothing more: the caller stops the model and
  replaces the reply.
- ``encoded_leak`` is the post-completion check of the whole answer, for disguised leaks the
  stream filter can't see: separated by punctuation, reversed, or base64-encoded. It can only
  log and flag: by the time the answer is complete, it has already been streamed.
"""

import base64
import re
import secrets
from typing import Literal

CANARY_BYTES = 10  # 20 hex characters

EncodedLeak = Literal["separated", "reversed", "base64"]

_BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{4,}={0,2}")


def new_canary() -> str:
    """A fresh random canary: 20 lower-case hex characters."""
    return secrets.token_hex(CANARY_BYTES)


def _normalised(text: str) -> str:
    return "".join(text.split()).lower()


class CanaryFilter:
    """Feed it the answer chunk by chunk; it returns the text that is safe to send so far."""

    def __init__(self, canary: str) -> None:
        self._canary = _normalised(canary)
        self._pending = ""
        self.leaked = False

    def feed(self, text: str) -> str:
        if self.leaked:
            return ""
        self._pending += text
        if self._canary in _normalised(self._pending):
            self.leaked = True
            self._pending = ""
            return ""
        # Hold back the last len(canary) non-whitespace characters: a canary still arriving
        # can only have started inside them.
        held = 0
        cut = len(self._pending)
        while cut > 0 and held < len(self._canary):
            cut -= 1
            if not self._pending[cut].isspace():
                held += 1
        if held < len(self._canary):
            return ""
        released, self._pending = self._pending[:cut], self._pending[cut:]
        return released

    def finish(self) -> str:
        """The answer is complete: the held-back text is safe (it was checked as it arrived)."""
        released, self._pending = self._pending, ""
        return released


def _decodes_to_canary(run: str, canary: str) -> bool:
    # Try each alignment: the encoded text may start part way into a base64 group.
    for offset in range(4):
        group = run[offset:].rstrip("=")
        # A last group of 2 or 3 characters is a padded one; 1 character can't be decoded.
        group = group[: len(group) - 1] if len(group) % 4 == 1 else group
        group += "=" * (-len(group) % 4)
        decoded = base64.b64decode(group, validate=True)
        if canary in decoded.decode("latin-1").lower():
            return True
    return False


def encoded_leak(text: str, canary: str) -> EncodedLeak | None:
    """How ``text`` gives the canary away in a form the stream filter doesn't match, if it
    does: with separators between its characters, reversed, or base64-encoded."""
    canary = canary.lower()
    letters = "".join(c for c in text.lower() if c.isalnum())
    if canary in letters:
        return "separated"
    if canary[::-1] in letters:
        return "reversed"
    joined = "".join(text.split())
    if any(_decodes_to_canary(run, canary) for run in _BASE64_RUN.findall(joined)):
        return "base64"
    return None
