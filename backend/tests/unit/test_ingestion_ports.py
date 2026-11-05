"""The settings choose the ingestion adapters; tasks find them once the API or worker has
installed them."""

import pytest

from app.core.settings import Settings
from app.documents import ports
from app.documents.converter import DoclingConverter, FakeConverter
from app.embeddings.fake import HashEmbedder
from app.embeddings.local import LocalEmbedder
from app.storage.memory import InMemoryObjectStore
from app.storage.s3 import S3ObjectStore
from tests.conftest import TEST_LOCAL_KEY_WRAPPER_KEY


def _settings(**values: str) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        local_key_wrapper_key=TEST_LOCAL_KEY_WRAPPER_KEY,
        **values,  # type: ignore[arg-type]
    )


def test_production_uses_s3_docling_and_the_local_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("OBJECT_STORE", "DOCUMENT_CONVERTER", "EMBEDDER"):
        monkeypatch.delenv(name, raising=False)

    chosen = ports.build_ports(_settings(object_store_endpoint_url="http://rustfs:9000"))

    assert isinstance(chosen.object_store, S3ObjectStore)
    assert isinstance(chosen.converter, DoclingConverter)
    assert list(chosen.embedders) == ["multilingual-e5-small"]
    assert isinstance(chosen.embedders["multilingual-e5-small"], LocalEmbedder)


def test_tests_use_the_in_memory_store_and_the_fakes() -> None:
    chosen = ports.build_ports(
        _settings(object_store="memory", document_converter="fake", embedder="fake")
    )

    assert isinstance(chosen.object_store, InMemoryObjectStore)
    assert isinstance(chosen.converter, FakeConverter)
    assert isinstance(chosen.embedders["multilingual-e5-small"], HashEmbedder)


def test_a_task_needs_the_adapters_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ports, "_installed", [])

    with pytest.raises(ports.PortsNotInstalledError):
        ports.current_ports()
