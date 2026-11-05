"""The deterministic hash-based embedder: the test fake for the embedder port.

The same text always gives the same unit-length vector, and different texts almost always give
different ones. Tokens are whitespace-separated words, so tests can reason about Chunk sizes.
"""

import hashlib
import math
import struct
from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

from app.embeddings.registry import LOCAL_MODEL, EmbeddingModel


class WordTokenizer(BaseTokenizer):
    """Counts whitespace-separated words as tokens."""

    max_tokens: int

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        return self.count_tokens


def hash_vector(text: str, dimension: int) -> list[float]:
    """A unit vector derived from the SHA-256 of ``text``."""
    raw: list[float] = []
    counter = 0
    while len(raw) < dimension:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        raw.extend(value / 2**31 - 1.0 for value in struct.unpack(">8I", digest))
        counter += 1
    vector = raw[:dimension]
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


class HashEmbedder:
    """Stands in for an Embedding Model (the local one unless told otherwise). Put errors in
    ``failures`` to make the next calls raise them, one per call."""

    def __init__(self, model: EmbeddingModel = LOCAL_MODEL) -> None:
        self._model = model
        self.failures: list[Exception] = []

    @property
    def model(self) -> EmbeddingModel:
        return self._model

    def tokenizer(self, max_tokens: int) -> BaseTokenizer:
        return WordTokenizer(max_tokens=max_tokens)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if self.failures:
            raise self.failures.pop(0)
        prefix = self._model.passage_prefix
        return [hash_vector(prefix + text, self._model.dimension) for text in texts]
