"""The adapters ingestion runs through: object store, document converter and embedders.

The API builds them at startup and installs them here; the worker does the same at its start.
Tasks read them with ``current_ports``. In tests the tasks run eagerly in the API's process,
so they share the API's fakes, which tests configure through ``app.state.ingestion``.
"""

from dataclasses import dataclass

from app.core.settings import Settings
from app.documents.converter import DoclingConverter, DocumentConverter, FakeConverter
from app.embeddings.fake import HashEmbedder
from app.embeddings.port import Embedder
from app.storage.factory import build_object_store
from app.storage.port import ObjectStore


@dataclass
class IngestionPorts:
    object_store: ObjectStore
    converter: DocumentConverter
    # By Embedding Model ID.
    embedders: dict[str, Embedder]


def _local_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "fake":
        return HashEmbedder()
    from app.embeddings.local import LocalEmbedder  # fastembed loads only when chosen

    return LocalEmbedder()


def build_ports(settings: Settings) -> IngestionPorts:
    converter: DocumentConverter = (
        FakeConverter() if settings.document_converter == "fake" else DoclingConverter()
    )
    embedder = _local_embedder(settings)
    return IngestionPorts(
        object_store=build_object_store(settings),
        converter=converter,
        embedders={embedder.model.id: embedder},
    )


class PortsNotInstalledError(RuntimeError):
    """A task ran before the API or worker installed the ingestion adapters."""


_installed: list[IngestionPorts] = []


def install_ports(ports: IngestionPorts) -> None:
    _installed[:] = [ports]


def current_ports() -> IngestionPorts:
    if not _installed:
        raise PortsNotInstalledError("The ingestion adapters haven't been installed")
    return _installed[0]
