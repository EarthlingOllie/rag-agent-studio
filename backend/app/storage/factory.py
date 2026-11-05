"""Builds the object store the settings select."""

from app.core.settings import Settings
from app.storage.memory import InMemoryObjectStore
from app.storage.port import ObjectStore
from app.storage.s3 import S3ObjectStore


def _url(value: object | None) -> str | None:
    return None if value is None else str(value).rstrip("/")


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.object_store == "memory":
        return InMemoryObjectStore()
    secret = settings.object_store_secret_access_key
    return S3ObjectStore(
        bucket=settings.object_store_bucket,
        endpoint_url=_url(settings.object_store_endpoint_url),
        public_endpoint_url=_url(settings.object_store_public_endpoint_url),
        region=settings.object_store_region,
        access_key_id=settings.object_store_access_key_id,
        secret_access_key=None if secret is None else secret.get_secret_value(),
    )
