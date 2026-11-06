"""The adapters ingestion runs through: object store, document converter, the local embedder,
the model gateway that provider Embedding Models are called through, and the injection
classifier the ingestion Guardrail scan uses.

The API builds them at startup and installs them here; the worker does the same at its start.
Tasks read them with ``current_ports``. In tests the tasks run eagerly in the API's process,
so they share the API's fakes, which tests configure through ``app.state.ingestion``.
"""

from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from app.core.settings import Settings
from app.crypto.envelope import EnvelopeEncryption
from app.documents.converter import DoclingConverter, DocumentConverter, FakeConverter
from app.embeddings.fake import HashEmbedder
from app.embeddings.port import Embedder
from app.gateway.adapters import build_model_gateway
from app.gateway.gateway import ModelGateway
from app.guardrails.classifier import InjectionClassifier
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.heuristic import HeuristicClassifier
from app.storage.factory import build_object_store
from app.storage.port import ObjectStore


@dataclass
class IngestionPorts:
    object_store: ObjectStore
    converter: DocumentConverter
    # The local embedders, by Embedding Model ID.
    embedders: dict[str, Embedder]
    # Builds the model gateway on an HTTP client. Each ingestion run opens its own client, on
    # its own event loop, and closes it when done.
    open_gateway: Callable[[httpx2.AsyncClient], ModelGateway]
    # Flags Chunks that look like instructions aimed at an AI.
    classifier: InjectionClassifier


def _local_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "fake":
        return HashEmbedder()
    from app.embeddings.local import LocalEmbedder  # fastembed loads only when chosen

    return LocalEmbedder()


def build_ports(settings: Settings, envelope: EnvelopeEncryption) -> IngestionPorts:
    converter: DocumentConverter = (
        FakeConverter() if settings.document_converter == "fake" else DoclingConverter()
    )
    embedder = _local_embedder(settings)
    classifier: InjectionClassifier = (
        RuleDrivenClassifier() if settings.injection_classifier == "fake" else HeuristicClassifier()
    )
    return IngestionPorts(
        object_store=build_object_store(settings),
        converter=converter,
        embedders={embedder.model.id: embedder},
        open_gateway=lambda client: build_model_gateway(settings, envelope, client),
        classifier=classifier,
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
