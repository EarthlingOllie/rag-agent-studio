"""The document-converter port: turns an uploaded file into Docling's document structure, from
which the markdown and the Chunks come. Production uses Docling; tests use the fake.

``ocr`` is the Project's OCR flag. With it on, text in images (scanned PDF pages) is read too;
with it off, conversion skips OCR, which is much faster.
"""

import re
from functools import cached_property
from io import BytesIO
from pathlib import PurePath
from typing import Protocol

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import RapidOcrOptions, ThreadedPdfPipelineOptions
from docling.document_converter import DocumentConverter as DoclingDocumentConverter
from docling.document_converter import PdfFormatOption
from docling_core.types.doc.base import BoundingBox, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.io import DocumentStream


class UnsupportedContentError(Exception):
    """The file's content can't be read: encrypted, damaged, or not what its type says."""


class DocumentConverter(Protocol):
    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        """The file's structure (headings, text, pages). ``filename`` gives the format; ``ocr``
        says whether to read text in images. Raises ``UnsupportedContentError`` for content it
        can't read; any other error is a failed conversion."""
        ...


def pdf_pipeline_options(*, ocr: bool) -> ThreadedPdfPipelineOptions:
    """Docling's default PDF pipeline, with OCR only when asked for. OCR runs through RapidOCR
    on ONNX Runtime (already used by the local Embedding Model), so it needs no PyTorch model
    of its own; its models are bundled with Docling's (the Dockerfile's ``download_models``)."""
    return ThreadedPdfPipelineOptions(
        do_ocr=ocr, ocr_options=RapidOcrOptions(backend="onnxruntime")
    )


class DoclingConverter:
    """Docling. Markdown, HTML, DOCX and PPTX need no models; PDF needs the layout models (and
    with OCR on, RapidOCR's), which the worker image bundles (the ``pdf`` dependency group).

    OCR only affects PDFs. One Docling converter is kept per setting, since each holds its
    loaded pipeline."""

    @cached_property
    def _converters(self) -> dict[bool, DoclingDocumentConverter]:
        return {
            ocr: DoclingDocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options(ocr=ocr))
                }
            )
            for ocr in (False, True)
        }

    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        stream = DocumentStream(name=filename, stream=BytesIO(data))
        return self._converters[ocr].convert(stream).document


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


# A file starting with this line stands for a scanned one: its text is only in images.
SCANNED_MARKER = "%SCANNED\n"
# A PDF starts with this; the fake skips that first line, so a test PDF is text after it.
PDF_HEADER = "%PDF-"


class FakeConverter:
    """Reads the file as UTF-8 text: ``#`` lines become headings, other lines paragraphs, and a
    form feed starts a new page. A first line starting ``%PDF-`` (a PDF's header) is skipped.
    A file starting with ``SCANNED_MARKER`` stands for a scanned
    one: its text is read only with ``ocr`` on, and otherwise its pages are empty, as Docling's
    are. Set ``failure`` to make the next conversions raise it."""

    def __init__(self) -> None:
        self.failure: Exception | None = None

    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        if self.failure is not None:
            raise self.failure
        document = DoclingDocument(name=PurePath(filename).stem)
        # Postgres text can't hold NUL, which binary files read as text would bring. A PDF's
        # header line is not content.
        text = data.decode("utf-8", errors="replace").replace("\x00", "")
        if text.startswith(PDF_HEADER):
            text = text.partition("\n")[2]
        scanned = text.startswith(SCANNED_MARKER)
        pages = text.removeprefix(SCANNED_MARKER).split("\f")
        for page_no, page in enumerate(pages, start=1):
            document.add_page(page_no=page_no, size=Size(width=595, height=842))
            if scanned and not ocr:
                continue
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
