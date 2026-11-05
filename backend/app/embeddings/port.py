"""The embedder port: turns Chunk texts into vectors for one Embedding Model.

The chunker counts tokens with the embedder's own tokenizer, so a Chunk never exceeds what the
model reads. Production uses the local model (fastembed); tests use the hash-based fake.
"""

from typing import Protocol

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

from app.embeddings.registry import EmbeddingModel


class Embedder(Protocol):
    @property
    def model(self) -> EmbeddingModel: ...

    def tokenizer(self, max_tokens: int) -> BaseTokenizer:
        """The model's tokenizer, limited to ``max_tokens`` per Chunk."""
        ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in order, each ``model.dimension`` long."""
        ...
