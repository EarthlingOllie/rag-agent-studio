"""The document-converter port: turns an uploaded file into Docling's document structure, from
which the markdown and the Chunks come. Production uses Docling; tests use the fake."""

import re
from functools import cached_property
from io import BytesIO
from pathlib import PurePath
from typing import Protocol

from docling.document_converter import DocumentConverter as DoclingDocumentConverter
from docling_core.types.doc.base import BoundingBox, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.io import DocumentStream


class DocumentConverter(Protocol):
    def convert(self, data: bytes, filename: str) -> DoclingDocument:
        """The file's structure (headings, text, pages). ``filename`` gives the format."""
        ...


class DoclingConverter:
    """Docling. Markdown, HTML, DOCX and PPTX need no models; PDF needs the layout models,
    which the worker image bundles (the ``pdf`` dependency group)."""

    @cached_property
    def _converter(self) -> DoclingDocumentConverter:
        return DoclingDocumentConverter()

    def convert(self, data: bytes, filename: str) -> DoclingDocument:
        result = self._converter.convert(DocumentStream(name=filename, stream=BytesIO(data)))
        return result.document


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class FakeConverter:
    """Reads the file as UTF-8 text: ``#`` lines become headings, other lines paragraphs, and a
    form feed starts a new page. Set ``failure`` to make the next conversions raise it."""

    def __init__(self) -> None:
        self.failure: Exception | None = None

    def convert(self, data: bytes, filename: str) -> DoclingDocument:
        if self.failure is not None:
            raise self.failure
        document = DoclingDocument(name=PurePath(filename).stem)
        pages = data.decode("utf-8", errors="replace").split("\f")
        for page_no, page in enumerate(pages, start=1):
            document.add_page(page_no=page_no, size=Size(width=595, height=842))
            paragraph: list[str] = []
            for line in [*page.splitlines(), ""]:
                heading = _HEADING.match(line)
                if paragraph and (heading or not line.strip()):
                    _add(document, " ".join(paragraph), page_no, heading_level=None)
                    paragraph = []
                if heading:
                    _add(document, heading[2], page_no, heading_level=len(heading[1]))
                elif line.strip():
                    paragraph.append(line.strip())
        return document


def _add(document: DoclingDocument, text: str, page_no: int, *, heading_level: int | None) -> None:
    prov = ProvenanceItem(
        page_no=page_no, bbox=BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, len(text))
    )
    if heading_level is None:
        document.add_text(label=DocItemLabel.TEXT, text=text, prov=prov)
    else:
        document.add_heading(text=text, level=heading_level, prov=prov)
