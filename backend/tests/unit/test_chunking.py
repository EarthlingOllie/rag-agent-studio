"""The converter-plus-chunker seam, on Docling output recorded from a live run.

``tests/fixtures/docling/*.json`` are what real Docling made of the sample DOCX and PPTX
(``tests/fixtures/record_docling_output.py``), so chunking is tested without running Docling.
"""

import json
from pathlib import Path

import pytest
from docling_core.types.doc.document import DoclingDocument

from app.documents.chunking import chunk_document
from app.embeddings.fake import WordTokenizer

RECORDED = Path(__file__).parents[1] / "fixtures" / "docling"


def recorded(name: str) -> DoclingDocument:
    return DoclingDocument.model_validate(json.loads((RECORDED / f"{name}.json").read_text()))


def test_a_word_document_is_chunked_by_section_with_its_heading_path() -> None:
    drafts = chunk_document(recorded("northwind-handbook.docx"), WordTokenizer(max_tokens=64))

    assert [(d.heading_path, d.page_start, d.page_end) for d in drafts] == [
        (["Northwind staff handbook", "Annual leave"], None, None),
        (["Northwind staff handbook", "Expenses"], None, None),
        (["Northwind staff handbook", "Working from home"], None, None),
    ]
    assert drafts[1].text == (
        "Claim expenses within 30 days with a receipt. Travel is booked through the travel desk."
    )
    # The headings travel with the text into the embedding.
    assert drafts[1].embedding_text == (
        "Northwind staff handbook\nExpenses\n"
        "Claim expenses within 30 days with a receipt. Travel is booked through the travel desk."
    )


def test_a_slide_deck_is_chunked_per_slide_with_page_numbers() -> None:
    drafts = chunk_document(recorded("northwind-handbook.pptx"), WordTokenizer(max_tokens=64))

    assert [(d.heading_path, d.page_start, d.page_end) for d in drafts] == [
        (["Northwind staff handbook"], 1, 1),
        (["Annual leave"], 2, 2),
        (["Expenses"], 3, 3),
        (["Working from home"], 4, 4),
    ]


@pytest.mark.parametrize("max_tokens", [12, 20])
def test_no_chunk_is_longer_than_the_tokenizers_limit(max_tokens: int) -> None:
    tokenizer = WordTokenizer(max_tokens=max_tokens)

    drafts = chunk_document(recorded("northwind-handbook.docx"), tokenizer)

    assert len(drafts) > 3  # the long sections were split
    assert max(tokenizer.count_tokens(d.embedding_text) for d in drafts) <= max_tokens
    assert "25 days of annual leave" in " ".join(d.text for d in drafts)
