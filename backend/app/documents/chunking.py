"""Chunking with Docling's ``HybridChunker``: structure-aware Chunks that fit the Embedding
Model, because tokens are counted with that model's own tokenizer."""

from dataclasses import dataclass

from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc.document import DoclingDocument


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    # What gets embedded: the text with its headings, so the vector carries their context.
    embedding_text: str


def embedding_text(heading_path: list[str], text: str) -> str:
    """What gets embedded for a Chunk: its headings, outermost first, then its text, one per
    line. Re-embedding rebuilds it from the stored Chunk, so a Chunk embeds the same way under
    every Embedding Model."""
    return "\n".join([*heading_path, text])


def chunk_document(document: DoclingDocument, tokenizer: BaseTokenizer) -> list[ChunkDraft]:
    chunker = HybridChunker(tokenizer=tokenizer)
    drafts = []
    for chunk in chunker.chunk(document):
        meta = DocChunk.model_validate(chunk).meta
        pages = sorted({prov.page_no for item in meta.doc_items for prov in item.prov})
        headings = list(meta.headings or [])
        drafts.append(
            ChunkDraft(
                text=chunk.text,
                heading_path=headings,
                page_start=pages[0] if pages else None,
                page_end=pages[-1] if pages else None,
                embedding_text=embedding_text(headings, chunk.text),
            )
        )
    return drafts
