"""argon2id password hashing."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError

# argon2-cffi's defaults follow RFC 9106's second recommended option; the type is pinned.
_hasher = PasswordHasher(type=Type.ID)

# Verified against when an email is unknown, so sign-in takes the same time either way.
_UNKNOWN_MEMBER_HASH = _hasher.hash("no member has this password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Checks a password; with no hash it still does the work of a check, then fails."""
    try:
        _hasher.verify(password_hash or _UNKNOWN_MEMBER_HASH, password)
    except VerificationError:
        return False
    return password_hash is not None
