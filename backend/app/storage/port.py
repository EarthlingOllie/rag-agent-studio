"""The object-store port. Production uses S3 (RustFS locally, the same adapter with another
endpoint); unit tests use the in-memory fake."""

from typing import Protocol


class ObjectNotFoundError(Exception):
    """No object is stored under that key."""


class ObjectStore(Protocol):
    async def prepare(self) -> None:
        """Makes the store ready to use (creates the bucket where that is allowed)."""
        ...

    def presign_put(self, key: str, *, content_type: str, expires_in: int) -> str:
        """A URL a browser can PUT the object's bytes to directly, for ``expires_in`` seconds."""
        ...

    async def put(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes:
        """The object's bytes; raises ``ObjectNotFoundError`` if there is none."""
        ...

    async def delete(self, key: str) -> None:
        """Removes the object; removing one that isn't there is not an error."""
        ...
