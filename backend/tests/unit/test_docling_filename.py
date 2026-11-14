"""Docling picks a file's format from its name. The name is the uploader's, so it can look like
a path; a valid file must convert whatever its name looks like (KB-F10)."""

import pytest

from app.documents.converter import DoclingConverter


@pytest.mark.parametrize(
    "filename",
    ["../../../etc/passwd.txt", "..\\..\\win.txt", ".hidden/notes.md", "a/b.md", "NOTES.TXT"],
)
def test_docling_converts_a_valid_file_whose_name_looks_like_a_path(filename: str) -> None:
    converted = DoclingConverter().convert(b"Everyone gets 25 days.\n", filename, ocr=False)

    assert converted.export_to_markdown() == "Everyone gets 25 days."


def test_docling_reads_the_format_from_the_extension_not_the_path() -> None:
    converted = DoclingConverter().convert(
        b"<html><body><h1>Leave</h1><p>Everyone gets 25 days.</p></body></html>",
        "../uploads.v2/page.html",
        ocr=False,
    )

    assert converted.export_to_markdown() == "# Leave\n\nEveryone gets 25 days."
