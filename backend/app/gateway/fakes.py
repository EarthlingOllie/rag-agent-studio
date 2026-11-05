"""The fake adapters: deterministic, offline stand-ins for every provider.

Tests and ``docker compose`` use them. A test that needs scripted replies passes its own
chat builder (for example one returning a Pydantic AI ``FunctionModel``).
"""

import hashlib
import math
import re
from collections.abc import Callable, Sequence

from pydantic_ai.embeddings import EmbeddingModel, EmbeddingResult, EmbeddingSettings
from pydantic_ai.embeddings.result import EmbedInputType
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from app.credentials.registry import Provider
from app.embeddings.registry import embedding_model
from app.gateway.ports import BedrockAccount, RankedDocument, Reranker

ChatBuilder = Callable[[Provider, str, str], Model]


def fake_chat(provider: Provider, secret: str, model: str) -> Model:
    """A Pydantic AI ``TestModel`` that says which provider and model it stands in for."""
    return TestModel(custom_output_text=f"Fake reply from {provider}:{model}.", model_name=model)


def _hash_vector(text: str, dimensions: int) -> list[float]:
    raw: list[float] = []
    counter = 0
    while len(raw) < dimensions:
        raw.extend(byte - 127.5 for byte in hashlib.sha256(f"{counter}:{text}".encode()).digest())
        counter += 1
    vector = raw[:dimensions]
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


class HashEmbeddingModel(EmbeddingModel):
    """The same text always gives the same unit vector, whether it is embedded as a document or
    a query; different texts differ. Vectors have the model's registered dimension, so they
    can be stored and searched like the real model's."""

    def __init__(self, model: str) -> None:
        super().__init__()
        self._model = model
        self._dimensions = embedding_model(model).dimension

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def system(self) -> str:
        return "fake"

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        texts, _ = self.prepare_embed(inputs, settings)
        return EmbeddingResult(
            [_hash_vector(text, self._dimensions) for text in texts],
            inputs=texts,
            input_type=input_type,
            model_name=self._model,
            provider_name=self.system,
        )


def _words(text: str) -> set[str]:
    # "Refunds" counts as "refund", so the fake behaves a little like a real reranker.
    return {word.removesuffix("s") for word in re.findall(r"[a-z]+", text.lower())}


class WordOverlapReranker:
    """Scores each document by the share of the query's words it contains."""

    def __init__(self, model: str) -> None:
        self.model_name = model

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[RankedDocument]:
        wanted = _words(query)
        scored = [
            RankedDocument(index, len(wanted & _words(document)) / max(len(wanted), 1))
            for index, document in enumerate(documents)
        ]
        ranked = sorted(scored, key=lambda ranked: (-ranked.score, ranked.index))
        return ranked[:top_k]


class FakeModelAdapters:
    def __init__(self, *, chat: ChatBuilder = fake_chat) -> None:
        self._chat = chat

    def chat(self, provider: Provider, secret: str, model: str) -> Model:
        return self._chat(provider, secret, model)

    def embedder(self, provider: Provider, secret: str, model: str) -> EmbeddingModel:
        return HashEmbeddingModel(model)

    def bedrock_embedder(self, account: BedrockAccount, model: str) -> EmbeddingModel:
        return HashEmbeddingModel(model)

    def reranker(self, provider: Provider, secret: str, model: str) -> Reranker:
        return WordOverlapReranker(model)
