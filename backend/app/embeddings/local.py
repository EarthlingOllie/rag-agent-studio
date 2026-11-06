"""The local Embedding Model: ``multilingual-e5-small`` through fastembed (ONNX, CPU).

The model and its tokenizer come from Hugging Face. The worker image downloads them at build
time; elsewhere they are fetched on first use. This adapter needs those downloads, so it is
exercised by the live suite (``tests/live``), outside the coverage gate (ADR-0008).
"""

import asyncio
from functools import cached_property

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

from app.embeddings.registry import LOCAL_MODEL, EmbeddingModel

# multilingual-e5-small isn't in fastembed's built-in list; its ONNX export is in the model repo.
_REGISTERED = False


def _register() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    TextEmbedding.add_custom_model(
        model=LOCAL_MODEL.tokenizer,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=ModelSource(hf=LOCAL_MODEL.tokenizer),
        dim=LOCAL_MODEL.dimension,
        model_file="onnx/model.onnx",
    )
    _REGISTERED = True


class LocalEmbedder:
    def __init__(self, cache_dir: str | None = None) -> None:
        self._cache_dir = cache_dir

    @property
    def model(self) -> EmbeddingModel:
        return LOCAL_MODEL

    @cached_property
    def _embedding(self) -> TextEmbedding:
        _register()
        return TextEmbedding(model_name=LOCAL_MODEL.tokenizer, cache_dir=self._cache_dir)

    def tokenizer(self, max_tokens: int) -> BaseTokenizer:
        return HuggingFaceTokenizer.from_pretrained(
            model_name=LOCAL_MODEL.tokenizer, max_tokens=max_tokens
        )

    def _passages(self, texts: list[str]) -> list[list[float]]:
        prefixed = [LOCAL_MODEL.passage_prefix + text for text in texts]
        return [vector.tolist() for vector in self._embedding.passage_embed(prefixed)]

    def _query(self, text: str) -> list[float]:
        (vector,) = self._embedding.query_embed([LOCAL_MODEL.query_prefix + text])
        result: list[float] = vector.tolist()
        return result

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        # ONNX inference is CPU-bound, so it runs off the event loop.
        return await asyncio.to_thread(self._passages, texts)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._query, text)
