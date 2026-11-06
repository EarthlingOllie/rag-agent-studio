"""The production document converter (Docling) on formats that need no models. PDF needs the
layout models (and, with OCR, RapidOCR's), so it is converted only in the live suite
(``tests/live``)."""

from pathlib import Path

import pytest
from docling.datamodel.pipeline_options import RapidOcrOptions

from app.documents.converter import DoclingConverter, pdf_pipeline_options

SAMPLES = Path(__file__).parents[1] / "fixtures" / "documents"


def test_docling_converts_markdown_with_its_headings() -> None:
    converted = DoclingConverter().convert(
        b"# Handbook\n\n## Leave\n\nEveryone gets 25 days.\n", "handbook.md", ocr=False
    )

    assert converted.export_to_markdown() == "# Handbook\n\n## Leave\n\nEveryone gets 25 days."


def test_docling_converts_a_word_document() -> None:
    converter = DoclingConverter()

    docx = (SAMPLES / "northwind-handbook.docx").read_bytes()
    converted = converter.convert(docx, "h.docx", ocr=False)

    markdown = converted.export_to_markdown()
    assert markdown.startswith("## Northwind staff handbook\n\n### Annual leave\n\n")
    assert "Claim expenses within 30 days with a receipt." in markdown


@pytest.mark.parametrize("ocr", [False, True])
def test_ocr_doesnt_change_formats_that_carry_their_own_text(ocr: bool) -> None:
    converted = DoclingConverter().convert(b"# Leave\n\nEveryone gets 25 days.\n", "l.md", ocr=ocr)

    assert converted.export_to_markdown() == "# Leave\n\nEveryone gets 25 days."


def test_docling_reads_pdfs_with_ocr_only_when_asked() -> None:
    with_ocr = pdf_pipeline_options(ocr=True)
    without_ocr = pdf_pipeline_options(ocr=False)

    assert (with_ocr.do_ocr, without_ocr.do_ocr) == (True, False)
    assert isinstance(with_ocr.ocr_options, RapidOcrOptions)
    assert with_ocr.ocr_options.backend == "onnxruntime"
