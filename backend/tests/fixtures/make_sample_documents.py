"""Writes the synthetic sample Documents (DOCX, PPTX, PDF) the Docling fixtures come from, and
a scanned PDF (text only in an image) for the OCR live test.

Run from ``backend/``: ``uv run python -m tests.fixtures.make_sample_documents``. The outputs are
committed; rerun only to change the samples, then rerun ``record_docling_output``.
"""

from datetime import UTC, datetime
from pathlib import Path

from docx import Document as WordDocument
from PIL import Image, ImageDraw, ImageFont
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


# How each kind of line is set in the PDF: font resource, size, and the space above it. The
# title and section headings are bold and larger, as in a real handbook, so Docling's layout
# model finds them; body paragraphs are 11-point Helvetica.
PDF_STYLES = {"title": ("F2", 20, 0), "heading": ("F2", 14, 30), "body": ("F1", 11, 18)}


def _pdf_text(lines: list[tuple[str, str]]) -> bytes:
    commands = ["BT"]
    y = 770
    for index, (style, line) in enumerate(lines):
        font, size, space_above = PDF_STYLES[style]
        y -= space_above if index else 0
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"/{font} {size} Tf 1 0 0 1 72 {y} Tm ({escaped}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def _section(index: int) -> list[tuple[str, str]]:
    heading, paragraphs = SECTIONS[index]
    return [("heading", heading), *(("body", paragraph) for paragraph in paragraphs)]


def write_pdf(path: Path) -> None:
    """A two-page, text-only PDF, written by hand so no PDF library is needed."""
    pages = [
        [("title", TITLE), *_section(0)],
        [*_section(1), *_section(2)],
    ]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [5 0 R 7 0 R] /Count 2 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    for index, lines in enumerate(pages):
        content_number = 6 + 2 * index
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 "
            f"0 R /F2 4 0 R >> >> /Contents {content_number} 0 R >>".encode()
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


def write_scanned_pdf(path: Path) -> None:
    """One A4 page that is only an image of text, as a scanner makes: no text layer, so only
    OCR can read it."""
    page = Image.new("L", (1240, 1754), color=255)  # A4 at 150 dpi
    draw = ImageDraw.Draw(page)
    draw.text((120, 150), SECTIONS[0][0], fill=0, font=ImageFont.load_default(size=64))
    body = ImageFont.load_default(size=36)
    lines = ["Everyone at Northwind Traders gets 25 days", "of annual leave a year."]
    for number, line in enumerate(lines):
        draw.text((120, 300 + 60 * number), line, fill=0, font=body)
    page.save(path, "PDF", resolution=150.0)


if __name__ == "__main__":
    write_docx(OUT / "northwind-handbook.docx")
    write_pptx(OUT / "northwind-handbook.pptx")
    write_pdf(OUT / "northwind-handbook.pdf")
    write_scanned_pdf(OUT / "scanned-leave-policy.pdf")
