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
from app.gateway.ports import RankedDocument, Reranker

FAKE_DIMENSIONS = 16
ChatBuilder = Callable[[Provider, str, str], Model]


def fake_chat(provider: Provider, secret: str, model: str) -> Model:
    """A Pydantic AI ``TestModel`` that says which provider and model it stands in for."""
    return TestModel(custom_output_text=f"Fake reply from {provider}:{model}.", model_name=model)


def _hash_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    raw = [byte - 127.5 for byte in digest[:FAKE_DIMENSIONS]]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


class HashEmbeddingModel(EmbeddingModel):
    """The same text always gives the same unit vector; different texts differ."""

    def __init__(self, model: str) -> None:
        super().__init__()
        self._model = model

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
            [_hash_vector(text) for text in texts],
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

    def reranker(self, provider: Provider, secret: str, model: str) -> Reranker:
        return WordOverlapReranker(model)
