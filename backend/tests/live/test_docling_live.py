"""Live suite: real Docling on the sample PDF, DOCX and PPTX, then chunked as ingestion does.

Run with ``make test-live``. PDF needs Docling's layout models (the ``pdf`` dependency group and
a Hugging Face download, or the worker image, which bundles them).
"""

from pathlib import Path

import pytest

from app.documents.chunking import chunk_document
from app.documents.converter import DoclingConverter
from app.embeddings.fake import WordTokenizer

SAMPLES = Path(__file__).parents[1] / "fixtures" / "documents"

pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    "sample", ["northwind-handbook.pdf", "northwind-handbook.docx", "northwind-handbook.pptx"]
)
def test_real_docling_converts_and_chunks_the_sample(sample: str) -> None:
    converted = DoclingConverter().convert((SAMPLES / sample).read_bytes(), sample)

    markdown = converted.export_to_markdown()
    assert "Northwind staff handbook" in markdown
    assert "Claim expenses within 30 days" in markdown
    drafts = chunk_document(converted, WordTokenizer(max_tokens=256))
    assert any("25 days of annual leave" in draft.text for draft in drafts)
    assert any("Expenses" in draft.heading_path for draft in drafts) or sample.endswith(".pdf")
