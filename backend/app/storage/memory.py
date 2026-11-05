"""The in-memory object store: the unit-test fake for the object-store port."""

from urllib.parse import quote

from app.storage.port import ObjectNotFoundError


class InMemoryObjectStore:
    """Objects in a dict. Presigned URLs use the ``memory://`` scheme; a test "uploads" by
    calling ``put`` with the key, as the browser would PUT to the URL."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def prepare(self) -> None:
        return None

    def presign_put(self, key: str, *, content_type: str, expires_in: int) -> str:
        return f"memory://objects/{quote(key)}"

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key][0]
        except KeyError:
            raise ObjectNotFoundError(key) from None

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
