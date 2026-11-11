"""The embedder port: turns Chunk texts and queries into vectors for one Embedding Model.

The chunker counts tokens with the embedder's own tokenizer, so a Chunk never exceeds what the
model reads. Production uses the local model (fastembed) or a provider model through the model
gateway (``app.embeddings.provider``); tests use the hash-based fake and the gateway's fakes.
"""

from typing import Protocol

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

from app.embeddings.registry import EmbeddingModel


class EmbeddingProviderError(Exception):
    """The Embedding Model's provider failed or didn't answer. Treated as transient: ingestion
    retries it with backoff before giving up."""


class Embedder(Protocol):
    @property
    def model(self) -> EmbeddingModel: ...

    def tokenizer(self, max_tokens: int) -> BaseTokenizer:
        """The model's tokenizer, limited to ``max_tokens`` per Chunk."""
        ...

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in order, each ``model.dimension`` long. Raises
        ``EmbeddingProviderError`` when the provider fails."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """The vector of a search query, to compare with passage vectors."""
        ...
