"""Records real Docling output for the sample Documents, for the converter-plus-chunker test.

Run from ``backend/``: ``uv run python -m tests.fixtures.record_docling_output``. It converts
each sample with the production Docling adapter and writes the DoclingDocument as JSON to
``tests/fixtures/docling/``. Tests load those files, so they don't run Docling to chunk.

The PDF needs Docling's layout model from Hugging Face and the ``pdf`` dependency group:
``uv run --group pdf python -m tests.fixtures.record_docling_output``. Where Hugging Face isn't
reachable, ``build_pdf_docling_fixture.py`` hand-builds the PDF file instead; recording here
replaces it with real output.
"""

import json
from pathlib import Path

from app.documents.converter import DoclingConverter

FIXTURES = Path(__file__).parent
SAMPLES = ["northwind-handbook.docx", "northwind-handbook.pptx", "northwind-handbook.pdf"]


def record() -> None:
    converter = DoclingConverter()
    for name in SAMPLES:
        document = converter.convert((FIXTURES / "documents" / name).read_bytes(), name)
        data = document.export_to_dict()
        (FIXTURES / "docling" / f"{name}.json").write_text(
            json.dumps(data, indent=1, sort_keys=True) + "\n"
        )


if __name__ == "__main__":
    record()
