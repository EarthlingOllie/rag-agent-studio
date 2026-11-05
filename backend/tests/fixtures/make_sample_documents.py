"""Writes the synthetic sample Documents (DOCX, PPTX, PDF) the Docling fixtures come from.

Run from ``backend/``: ``uv run python -m tests.fixtures.make_sample_documents``. The outputs are
committed; rerun only to change the samples, then rerun ``record_docling_output``.
"""

from datetime import UTC, datetime
from pathlib import Path

from docx import Document as WordDocument
from pptx import Presentation

OUT = Path(__file__).parent / "documents"

SECTIONS = [
    (
        "Annual leave",
        [
            "Everyone at Northwind Traders gets 25 days of annual leave a year, plus public "
            "holidays.",
            "Book leave in the HR portal at least two weeks ahead. Your manager approves it.",
        ],
    ),
    (
        "Expenses",
        [
            "Claim expenses within 30 days with a receipt. Travel is booked through the travel "
            "desk.",
        ],
    ),
    (
        "Working from home",
        ["You can work from home up to three days a week. Agree the days with your team."],
    ),
]
TITLE = "Northwind staff handbook"


def write_docx(path: Path) -> None:
    document = WordDocument()
    document.add_heading(TITLE, level=1)
    for heading, paragraphs in SECTIONS:
        document.add_heading(heading, level=2)
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
    document.core_properties.created = datetime(2026, 1, 1, tzinfo=UTC)
    document.save(str(path))


def write_pptx(path: Path) -> None:
    deck = Presentation()
    title_slide = deck.slides.add_slide(deck.slide_layouts[0])
    title_slide.shapes.title.text = TITLE
    title_slide.placeholders[1].text = "Synthetic sample for tests"
    for heading, paragraphs in SECTIONS:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = heading
        slide.placeholders[1].text = "\n".join(paragraphs)
    deck.save(str(path))


def _pdf_text(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf", "72 770 Td", "16 TL"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def write_pdf(path: Path) -> None:
    """A two-page, text-only PDF, written by hand so no PDF library is needed."""
    pages = [
        [TITLE, "", SECTIONS[0][0], *SECTIONS[0][1]],
        [SECTIONS[1][0], *SECTIONS[1][1], "", SECTIONS[2][0], *SECTIONS[2][1]],
    ]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, lines in enumerate(pages):
        content_number = 5 + 2 * index
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 "
            f"0 R >> >> /Contents {content_number} 0 R >>".encode()
        )
        stream = _pdf_text(lines)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        output += b"%010d 00000 n \n" % offset
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(bytes(output))


if __name__ == "__main__":
    write_docx(OUT / "northwind-handbook.docx")
    write_pptx(OUT / "northwind-handbook.pptx")
    write_pdf(OUT / "northwind-handbook.pdf")
