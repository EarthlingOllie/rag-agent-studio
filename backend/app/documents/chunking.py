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


def chunk_document(document: DoclingDocument, tokenizer: BaseTokenizer) -> list[ChunkDraft]:
    chunker = HybridChunker(tokenizer=tokenizer)
    drafts = []
    for chunk in chunker.chunk(document):
        meta = DocChunk.model_validate(chunk).meta
        pages = sorted({prov.page_no for item in meta.doc_items for prov in item.prov})
        drafts.append(
            ChunkDraft(
                text=chunk.text,
                heading_path=list(meta.headings or []),
                page_start=pages[0] if pages else None,
                page_end=pages[-1] if pages else None,
                embedding_text=chunker.contextualize(chunk),
            )
        )
    return drafts
