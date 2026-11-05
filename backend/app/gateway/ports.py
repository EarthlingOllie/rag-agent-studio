"""What the gateway builds, and the adapters port it builds them through.

Chat models are Pydantic AI ``Model``s and embedders are Pydantic AI ``EmbeddingModel``s.
Pydantic AI has no reranking, so ``Reranker`` is this project's own small port.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model

from app.credentials.registry import Provider


@dataclass(frozen=True)
class RankedDocument:
    """One document's place in a reranking: its index in the input and its relevance score."""

    index: int
    score: float


class Reranker(Protocol):
    @property
    def model_name(self) -> str: ...

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[RankedDocument]:
        """The documents, most relevant first; only the first ``top_k`` when it is given."""
        ...


class ModelAdapters(Protocol):
    """Builds clients for a provider from its secret. Production calls the providers; the
    fake (tests, ``docker compose``) answers deterministically without any network."""

    def chat(self, provider: Provider, secret: str, model: str) -> Model: ...

    def embedder(self, provider: Provider, secret: str, model: str) -> EmbeddingModel: ...

    def reranker(self, provider: Provider, secret: str, model: str) -> Reranker: ...
