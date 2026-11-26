"""The document-converter port: turns an uploaded file into Docling's document structure, from
which the markdown and the Chunks come. Production uses Docling; tests use the fake.

``ocr`` is the Project's OCR flag. With it on, text in images (scanned PDF pages) is read too;
with it off, conversion skips OCR, which is much faster.
"""

import hashlib
import re
import tempfile
from functools import cached_property
from io import BytesIO
from pathlib import Path, PurePath
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

from app.jobs.faults import JobKilled, KillSwitch


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


# Test-only: a file whose first line starts with this is interrupted at its first conversion, as
# if the worker died there (``JobKilled``, so no error handling runs), and converted normally
# after that. The rest of the line can carry anything (a unique token, so each run's file is new).
INTERRUPT_MARKER = "%INTERRUPT-ONCE "


def interrupt_if_marked(data: bytes) -> bytes:
    """Raises ``JobKilled`` the first time a file carrying ``INTERRUPT_MARKER`` is converted; on
    later conversions returns it without the marker line. Which files have been interrupted is
    kept in the temporary directory, so it holds across a worker's processes and restarts."""
    if not data.startswith(INTERRUPT_MARKER.encode()):
        return data
    digest = hashlib.sha256(data).hexdigest()
    sentinel = Path(tempfile.gettempdir()) / f"converter-interrupted-{digest}"
    try:
        sentinel.touch(exist_ok=False)
    except FileExistsError:
        return data.partition(b"\n")[2]
    raise JobKilled("convert")


class InterruptibleConverter:
    """Test-only (``CONVERTER_TEST_INTERRUPTS``): any converter, with the fake converter's
    ``INTERRUPT_MARKER`` switch in front, so an end-to-end test can interrupt an ingestion on a
    stack that converts with Docling."""

    def __init__(self, converter: DocumentConverter) -> None:
        self.converter = converter

    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        return self.converter.convert(interrupt_if_marked(data), filename, ocr=ocr)


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
    are. Set ``failure`` to make the next conversions raise it; arm ``kill`` at ``"convert"`` to
    kill the job at its next conversion. A file starting with ``INTERRUPT_MARKER`` is
    interrupted at its first conversion (``interrupt_if_marked``)."""

    def __init__(self) -> None:
        self.failure: Exception | None = None
        self.kill = KillSwitch()

    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        self.kill.check("convert")
        if self.failure is not None:
            raise self.failure
        data = interrupt_if_marked(data)
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
