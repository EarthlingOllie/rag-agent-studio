"""Live suite: real Docling on the sample PDF, DOCX and PPTX, then chunked as ingestion does.

Run with ``make test-live``. PDF needs Docling's layout models (the ``pdf`` dependency group and
a Hugging Face download, or the worker image, which bundles them); without them the PDF case is
skipped with the reason, unless ``LIVE_REQUIRE_MODELS=1``. The scanned PDF also needs RapidOCR's
models, for OCR.
"""

from pathlib import Path

import pytest

from app.documents.chunking import chunk_document
from app.documents.converter import DoclingConverter
from app.embeddings.fake import WordTokenizer
from tests.live.models import DOCLING_LAYOUT, require_models, require_ocr_models

SAMPLES = Path(__file__).parents[1] / "fixtures" / "documents"

pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    "sample", ["northwind-handbook.pdf", "northwind-handbook.docx", "northwind-handbook.pptx"]
)
def test_real_docling_converts_and_chunks_the_sample(sample: str) -> None:
    if sample.endswith(".pdf"):
        require_models(DOCLING_LAYOUT)
    converted = DoclingConverter().convert((SAMPLES / sample).read_bytes(), sample, ocr=False)

    markdown = converted.export_to_markdown()
    assert "Northwind staff handbook" in markdown
    assert "Claim expenses within 30 days" in markdown
    drafts = chunk_document(converted, WordTokenizer(max_tokens=256))
    assert any("25 days of annual leave" in draft.text for draft in drafts)
    assert any("Expenses" in draft.heading_path for draft in drafts) or sample.endswith(".pdf")


def test_real_docling_reads_a_scanned_pdf_only_with_ocr() -> None:
    """The scanned sample is an image of text, with no text layer (``make_sample_documents``)."""
    require_models(DOCLING_LAYOUT)
    require_ocr_models()
    scanned = (SAMPLES / "scanned-leave-policy.pdf").read_bytes()
    converter = DoclingConverter()

    with_ocr = converter.convert(scanned, "scanned-leave-policy.pdf", ocr=True)
    without_ocr = converter.convert(scanned, "scanned-leave-policy.pdf", ocr=False)

    assert "25 days" in with_ocr.export_to_markdown()
    assert "annual leave" in with_ocr.export_to_markdown()
    assert "25 days" not in without_ocr.export_to_markdown()
    drafts = chunk_document(with_ocr, WordTokenizer(max_tokens=256))
    assert any("25 days" in draft.text for draft in drafts)
