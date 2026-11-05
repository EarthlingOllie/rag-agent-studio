"""Hand-builds ``tests/fixtures/docling/northwind-handbook.pdf.json`` until it can be recorded.

Recording real Docling output for the sample PDF needs Docling's layout model from Hugging Face
(``record_docling_output.py`` with the ``pdf`` dependency group). Where that download isn't
possible, this script writes a DoclingDocument in the shape Docling's PDF pipeline produces for
the sample: the title, flat level-1 section headers, one text item per paragraph, a page per PDF
page (595 x 842 points) and provenance with bottom-left bounding boxes taken from the sample's
own text positions (``make_sample_documents.write_pdf``: x 72, first baseline 770, leading 16).

Run from ``backend/``: ``uv run python -m tests.fixtures.build_pdf_docling_fixture``. Once
Hugging Face is reachable, ``record_docling_output.py`` overwrites the file with real output.
"""

import json
from pathlib import Path

from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from tests.fixtures.make_sample_documents import SECTIONS, TITLE

FIXTURES = Path(__file__).parent
PAGE = Size(width=595, height=842)
# Helvetica at 12 points: about 6 points per character is close enough for a bounding box.
CHAR_WIDTH = 6.0


def _prov(page_no: int, line: int, text: str) -> ProvenanceItem:
    baseline = 770 - 16 * line
    return ProvenanceItem(
        page_no=page_no,
        bbox=BoundingBox(
            l=72,
            t=baseline + 9,
            r=72 + CHAR_WIDTH * len(text),
            b=baseline - 3,
            coord_origin=CoordOrigin.BOTTOMLEFT,
        ),
        charspan=(0, len(text)),
    )


def build() -> DoclingDocument:
    document = DoclingDocument(name="northwind-handbook")
    # The same lines, pages and blank lines as the sample PDF.
    pages: list[list[str]] = [
        [TITLE, "", SECTIONS[0][0], *SECTIONS[0][1]],
        [SECTIONS[1][0], *SECTIONS[1][1], "", SECTIONS[2][0], *SECTIONS[2][1]],
    ]
    headings = {heading for heading, _ in SECTIONS}
    for page_no, lines in enumerate(pages, start=1):
        document.add_page(page_no=page_no, size=PAGE)
        for line, text in enumerate(lines):
            if not text:
                continue
            prov = _prov(page_no, line, text)
            if text == TITLE:
                document.add_title(text=text, prov=prov)
            elif text in headings:
                document.add_heading(text=text, level=1, prov=prov)
            else:
                document.add_text(label=DocItemLabel.TEXT, text=text, prov=prov)
    return document


def write() -> None:
    data = build().export_to_dict()
    (FIXTURES / "docling" / "northwind-handbook.pdf.json").write_text(
        json.dumps(data, indent=1, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    write()
