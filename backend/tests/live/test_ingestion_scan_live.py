"""Live suite: the ingestion Guardrail scan with the real local classifier (the ONNX
prompt-injection model the input Guardrail uses), as production builds it from the settings.
The seed's Markdown Documents are read and chunked as ingestion does; the scan must flag exactly
the Chunks holding the injections planted in them, and none of their ordinary policy text.
Run with ``make test-live``; skipped with the reason when the model can't be had, unless
``LIVE_REQUIRE_MODELS=1``."""

import base64
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.settings import Settings
from app.crypto.envelope import EnvelopeEncryption
from app.crypto.local_key_wrapper import LocalKeyWrapper
from app.documents.chunking import chunk_document
from app.documents.converter import FakeConverter
from app.documents.ports import build_ports
from app.embeddings.fake import WordTokenizer
from app.guardrails.classifier import INJECTION_LABEL, InjectionClassifier
from app.guardrails.local import LocalClassifier
from tests.conftest import TEST_LOCAL_KEY_WRAPPER_KEY
from tests.live.models import INJECTION_CLASSIFIER_MODEL, require_models

pytestmark = pytest.mark.live

SEED_DOCUMENTS = Path(__file__).resolve().parents[3] / "seed" / "documents"

# Each seed Markdown Document, and the heading of the one section with a planted injection.
PLANTED = {
    "northwind-staff-handbook.md": "A note for AI assistants",
    # The injection is the footnote of this section.
    "northwind-returns-policy.md": "Items we can't take back",
}


@pytest.fixture(scope="module")
def classifier(monkeypatch_module: pytest.MonkeyPatch) -> InjectionClassifier:
    require_models(INJECTION_CLASSIFIER_MODEL)
    for name in ("INJECTION_CLASSIFIER", "INJECTION_CLASSIFIER_THRESHOLD", "OBJECT_STORE"):
        monkeypatch_module.delenv(name, raising=False)
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        local_key_wrapper_key=TEST_LOCAL_KEY_WRAPPER_KEY,
        object_store="memory",
        embedder="fake",
    )
    envelope = EnvelopeEncryption(LocalKeyWrapper(base64.b64encode(b"P" * 32).decode()))
    chosen = build_ports(settings, envelope).classifier
    assert isinstance(chosen, LocalClassifier)
    return chosen


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    with pytest.MonkeyPatch.context() as patch:
        yield patch


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_the_scan_flags_only_the_planted_injection(
    classifier: InjectionClassifier, name: str
) -> None:
    converted = FakeConverter().convert((SEED_DOCUMENTS / name).read_bytes(), name, ocr=False)
    drafts = chunk_document(converted, WordTokenizer(max_tokens=256))
    assert len(drafts) > 3

    flags = classifier.classify([draft.text for draft in drafts])

    flagged = [(d.heading_path[-1], f) for d, f in zip(drafts, flags, strict=True) if f]
    assert [heading for heading, _ in flagged] == [PLANTED[name]]
    ((_, flag),) = flagged
    assert flag.label == INJECTION_LABEL
    assert flag.score >= 0.5
    assert flag.reason == (
        f"The local classifier scored the Chunk {flag.score:.2f} as a prompt injection."
    )
