"""The envelope-encryption module, through its public interface: seal and open.

It has no HTTP surface of its own, so this is the highest seam for the format guarantees;
the MFA API tests cover it in use.
"""

import base64

import pytest

from app.crypto.envelope import EnvelopeEncryption, EnvelopeError
from app.crypto.local_key_wrapper import LocalKeyWrapper

KEY_A = base64.b64encode(b"A" * 32).decode()
KEY_B = base64.b64encode(b"B" * 32).decode()
CONTEXT = b"mfa-totp:member-1"


def _envelope(key: str = KEY_A) -> EnvelopeEncryption:
    return EnvelopeEncryption(LocalKeyWrapper(key))


def test_open_returns_what_was_sealed() -> None:
    envelope = _envelope()

    sealed = envelope.seal(b"JBSWY3DPEHPK3PXP", context=CONTEXT)

    assert envelope.open(sealed, context=CONTEXT) == b"JBSWY3DPEHPK3PXP"
    assert b"JBSWY3DPEHPK3PXP" not in sealed


def test_every_record_gets_a_fresh_data_key_and_nonce() -> None:
    envelope = _envelope()

    first = envelope.seal(b"same secret", context=CONTEXT)
    second = envelope.seal(b"same secret", context=CONTEXT)

    assert first != second
    # The wrapped data keys differ, not just the nonces: the header up to the nonce differs.
    assert (
        first[: len(first) - 12 - 16 - len(b"same secret")]
        != second[: len(second) - 12 - 16 - len(b"same secret")]
    )


def test_the_format_starts_with_version_1_and_names_the_wrapping_key() -> None:
    wrapper = LocalKeyWrapper(KEY_A)

    sealed = EnvelopeEncryption(wrapper).seal(b"secret", context=CONTEXT)

    assert sealed[0] == 1
    key_id_length = sealed[1]
    assert sealed[2 : 2 + key_id_length].decode() == wrapper.key_id
    assert wrapper.key_id.startswith("local:")
    assert wrapper.key_id != LocalKeyWrapper(KEY_B).key_id


@pytest.mark.parametrize("position", [0, 1, 5, 30, 60, -20, -1])
def test_tampering_with_any_byte_is_detected(position: int) -> None:
    envelope = _envelope()
    sealed = bytearray(envelope.seal(b"a TOTP secret", context=CONTEXT))

    sealed[position] ^= 0x01

    with pytest.raises(EnvelopeError):
        envelope.open(bytes(sealed), context=CONTEXT)


def test_truncated_records_are_refused() -> None:
    envelope = _envelope()
    sealed = envelope.seal(b"a TOTP secret", context=CONTEXT)

    for length in (0, 1, 2, 10, 40, len(sealed) - 1):
        with pytest.raises(EnvelopeError):
            envelope.open(sealed[:length], context=CONTEXT)


def test_a_record_moved_to_another_context_does_not_open() -> None:
    envelope = _envelope()
    sealed = envelope.seal(b"a TOTP secret", context=b"mfa-totp:member-1")

    with pytest.raises(EnvelopeError):
        envelope.open(sealed, context=b"mfa-totp:member-2")


def test_a_record_sealed_under_another_key_does_not_open() -> None:
    sealed = _envelope(KEY_A).seal(b"a TOTP secret", context=CONTEXT)

    with pytest.raises(EnvelopeError, match="key"):
        _envelope(KEY_B).open(sealed, context=CONTEXT)


def test_a_wrapped_key_under_the_right_key_id_but_tampered_is_refused() -> None:
    wrapper = LocalKeyWrapper(KEY_A)

    with pytest.raises(EnvelopeError):
        wrapper.unwrap(wrapper.key_id, b"\x00" * 60)


def test_unknown_format_versions_are_refused() -> None:
    envelope = _envelope()
    sealed = envelope.seal(b"a TOTP secret", context=CONTEXT)

    with pytest.raises(EnvelopeError, match="version"):
        envelope.open(b"\x02" + sealed[1:], context=CONTEXT)


@pytest.mark.parametrize("key", ["not base64!", base64.b64encode(b"short").decode()])
def test_the_local_key_wrapper_needs_a_32_byte_base64_key(key: str) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        LocalKeyWrapper(key)
