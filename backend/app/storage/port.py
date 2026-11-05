"""The object-store port. Production uses S3 (RustFS locally, the same adapter with another
endpoint); unit tests use the in-memory fake."""

from typing import Protocol
from urllib.parse import quote


class ObjectNotFoundError(Exception):
    """No object is stored under that key."""


def attachment_disposition(filename: str) -> str:
    """A ``Content-Disposition`` that saves the download as ``filename``: an ASCII fallback
    for old browsers, and the exact name, percent-encoded as UTF-8 (RFC 6266)."""
    fallback = "".join(
        c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in filename
    )
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


class ObjectStore(Protocol):
    async def prepare(self) -> None:
        """Makes the store ready to use (creates the bucket where that is allowed)."""
        ...

    def presign_put(self, key: str, *, content_type: str, expires_in: int) -> str:
        """A URL a browser can PUT the object's bytes to directly, for ``expires_in`` seconds."""
        ...

    def presign_get(self, key: str, *, filename: str, content_type: str, expires_in: int) -> str:
        """A URL a browser can GET the object from directly, for ``expires_in`` seconds. The
        store answers it as an attachment named ``filename``, with ``content_type``."""
        ...

    async def put(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes:
        """The object's bytes; raises ``ObjectNotFoundError`` if there is none."""
        ...

    async def delete(self, key: str) -> None:
        """Removes the object; removing one that isn't there is not an error."""
        ...
