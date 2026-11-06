"""The in-memory object store: the unit-test fake for the object-store port."""

from urllib.parse import quote, urlencode

from app.storage.port import ObjectNotFoundError, attachment_disposition


class InMemoryObjectStore:
    """Objects in a dict. Presigned URLs use the ``memory://`` scheme; a test "uploads" by
    calling ``put`` with the key, as the browser would PUT to the URL. Set ``failure`` to make
    reads raise it."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.failure: Exception | None = None

    async def prepare(self) -> None:
        return None

    def presign_put(self, key: str, *, content_type: str, expires_in: int) -> str:
        return f"memory://objects/{quote(key)}"

    def presign_get(self, key: str, *, filename: str, content_type: str, expires_in: int) -> str:
        query = urlencode(
            {
                "response-content-type": content_type,
                "response-content-disposition": attachment_disposition(filename),
                "expires-in": expires_in,
            }
        )
        return f"memory://objects/{quote(key)}?{query}"

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        if self.failure is not None:
            raise self.failure
        try:
            return self.objects[key][0]
        except KeyError:
            raise ObjectNotFoundError(key) from None

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
