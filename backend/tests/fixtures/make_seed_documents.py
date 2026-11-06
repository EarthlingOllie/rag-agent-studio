"""Writes the seed's Word and PowerPoint Documents from their markdown sources.

The sources are ``seed/sources/*.md``: a ``#`` title, an intro paragraph, then ``##`` sections
of paragraphs. ``northwind-product-faq.md`` becomes a DOCX and ``northwind-spring-range.md`` a
PPTX (a title slide, then a slide per section), in ``seed/documents``.

Run from ``backend/``: ``uv run python -m tests.fixtures.make_seed_documents``. The outputs are
committed; rerun only to change the sources.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from docx import Document as WordDocument
from pptx import Presentation

SEED = Path(__file__).parents[3] / "seed"


@dataclass(frozen=True)
class Source:
    title: str
    intro: str
    sections: list[tuple[str, str]]


def read_source(path: Path) -> Source:
    title, intro = "", ""
    sections: list[tuple[str, list[str]]] = []
    for block in path.read_text().strip().split("\n\n"):
        text = " ".join(block.split())
        if text.startswith("## "):
            sections.append((text.removeprefix("## "), []))
        elif text.startswith("# "):
            title = text.removeprefix("# ")
        elif sections:
            sections[-1][1].append(text)
        else:
            intro = text
    return Source(title, intro, [(heading, " ".join(body)) for heading, body in sections])


def write_docx(source: Source, path: Path) -> None:
    document = WordDocument()
    document.add_heading(source.title, level=1)
    document.add_paragraph(source.intro)
    for heading, body in source.sections:
        document.add_heading(heading, level=2)
        document.add_paragraph(body)
    document.core_properties.created = datetime(2026, 11, 6, tzinfo=UTC)
    document.core_properties.title = source.title
    document.save(str(path))


def write_pptx(source: Source, path: Path) -> None:
    deck = Presentation()
    title_slide = deck.slides.add_slide(deck.slide_layouts[0])
    title_slide.shapes.title.text = source.title
    title_slide.placeholders[1].text = source.intro
    for heading, body in source.sections:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = heading
        slide.placeholders[1].text = body
    deck.save(str(path))


if __name__ == "__main__":
    write_docx(
        read_source(SEED / "sources" / "northwind-product-faq.md"),
        SEED / "documents" / "northwind-product-faq.docx",
    )
    write_pptx(
        read_source(SEED / "sources" / "northwind-spring-range.md"),
        SEED / "documents" / "northwind-spring-range.pptx",
    )
