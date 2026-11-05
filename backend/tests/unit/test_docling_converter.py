"""The production document converter (Docling) on formats that need no models. PDF needs the
layout models, so it is converted only in the live suite (``tests/live``)."""

from pathlib import Path

from app.documents.converter import DoclingConverter

SAMPLES = Path(__file__).parents[1] / "fixtures" / "documents"


def test_docling_converts_markdown_with_its_headings() -> None:
    converted = DoclingConverter().convert(
        b"# Handbook\n\n## Leave\n\nEveryone gets 25 days.\n", "handbook.md"
    )

    assert converted.export_to_markdown() == "# Handbook\n\n## Leave\n\nEveryone gets 25 days."


def test_docling_converts_a_word_document() -> None:
    converter = DoclingConverter()

    converted = converter.convert((SAMPLES / "northwind-handbook.docx").read_bytes(), "h.docx")

    markdown = converted.export_to_markdown()
    assert markdown.startswith("## Northwind staff handbook\n\n### Annual leave\n\n")
    assert "Claim expenses within 30 days with a receipt." in markdown
