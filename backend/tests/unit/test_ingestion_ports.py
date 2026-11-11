"""The settings choose the ingestion adapters; tasks find them once the API or worker has
installed them."""

import base64

import httpx2
import pytest

from app.core.settings import Settings
from app.crypto.envelope import EnvelopeEncryption
from app.crypto.local_key_wrapper import LocalKeyWrapper
from app.documents import ports
from app.documents.converter import DoclingConverter, FakeConverter
from app.embeddings.fake import HashEmbedder
from app.embeddings.local import LocalEmbedder
from app.gateway.fakes import FakeModelAdapters
from app.gateway.live import LiveModelAdapters
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.heuristic import HeuristicClassifier
from app.guardrails.local import LocalClassifier
from app.storage.memory import InMemoryObjectStore
from app.storage.s3 import S3ObjectStore
from tests.conftest import TEST_LOCAL_KEY_WRAPPER_KEY

ENVELOPE = EnvelopeEncryption(LocalKeyWrapper(base64.b64encode(b"P" * 32).decode()))


def _settings(**values: str) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        local_key_wrapper_key=TEST_LOCAL_KEY_WRAPPER_KEY,
        **values,  # type: ignore[arg-type]
    )


def test_production_uses_s3_docling_the_local_embedding_model_and_the_local_classifier_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OBJECT_STORE",
        "DOCUMENT_CONVERTER",
        "EMBEDDER",
        "INJECTION_CLASSIFIER",
        "INJECTION_CLASSIFIER_THRESHOLD",
    ):
        monkeypatch.delenv(name, raising=False)

    chosen = ports.build_ports(_settings(object_store_endpoint_url="http://rustfs:9000"), ENVELOPE)

    assert isinstance(chosen.object_store, S3ObjectStore)
    assert isinstance(chosen.converter, DoclingConverter)
    assert list(chosen.embedders) == ["multilingual-e5-small"]
    assert isinstance(chosen.embedders["multilingual-e5-small"], LocalEmbedder)
    # The ingestion scan reads Chunks with the local ONNX model (loaded on first use, so not
    # here), at the same default threshold as the input Guardrail, and says it judged a Chunk.
    assert isinstance(chosen.classifier, LocalClassifier)
    assert (chosen.classifier.threshold, chosen.classifier.subject) == (0.5, "Chunk")


def test_the_settings_tune_the_scans_threshold_or_choose_the_heuristic_baseline() -> None:
    tuned = ports.build_ports(
        _settings(object_store="memory", injection_classifier_threshold="0.9"), ENVELOPE
    )
    heuristic = ports.build_ports(
        _settings(object_store="memory", injection_classifier="heuristic"), ENVELOPE
    )

    assert isinstance(tuned.classifier, LocalClassifier)
    assert tuned.classifier.threshold == 0.9
    assert isinstance(heuristic.classifier, HeuristicClassifier)


async def test_ingestion_calls_provider_models_through_the_gateway_the_settings_choose() -> None:
    live = ports.build_ports(_settings(object_store="memory", model_gateway="live"), ENVELOPE)
    fake = ports.build_ports(_settings(object_store="memory", model_gateway="fake"), ENVELOPE)

    async with httpx2.AsyncClient() as client:
        assert isinstance(live.open_gateway(client).adapters, LiveModelAdapters)
        assert isinstance(fake.open_gateway(client).adapters, FakeModelAdapters)


def test_tests_use_the_in_memory_store_and_the_fakes() -> None:
    chosen = ports.build_ports(
        _settings(
            object_store="memory",
            document_converter="fake",
            embedder="fake",
            injection_classifier="fake",
        ),
        ENVELOPE,
    )

    assert isinstance(chosen.object_store, InMemoryObjectStore)
    assert isinstance(chosen.converter, FakeConverter)
    assert isinstance(chosen.embedders["multilingual-e5-small"], HashEmbedder)
    assert isinstance(chosen.classifier, RuleDrivenClassifier)


def test_a_task_needs_the_adapters_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ports, "_installed", [])

    with pytest.raises(ports.PortsNotInstalledError):
        ports.current_ports()
