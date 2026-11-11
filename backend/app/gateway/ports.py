"""What the gateway builds, and the adapters port it builds them through.

Chat models are Pydantic AI ``Model``s and embedders are Pydantic AI ``EmbeddingModel``s.
Pydantic AI has no reranking, so ``Reranker`` is this project's own small port.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model

from app.credentials.registry import Provider


@dataclass(frozen=True)
class RankedDocument:
    """One document's place in a reranking: its index in the input and its relevance score."""

    index: int
    score: float


@dataclass(frozen=True)
class BedrockAccount:
    """Where Bedrock is called, and as whom: an IAM role in the Owner's account, which the
    platform assumes with the Organisation's external ID, or an IAM user's access keys."""

    region: str
    role_arn: str | None = None
    external_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = field(default=None, repr=False)


class Reranker(Protocol):
    @property
    def model_name(self) -> str: ...

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[RankedDocument]:
        """The documents, most relevant first; only the first ``top_k`` when it is given."""
        ...


class ModelAdapters(Protocol):
    """Builds clients for a provider from its secret (Bedrock embedders: from its account).
    Production calls the providers; the fake (tests, ``docker compose``) answers
    deterministically without any network."""

    def chat(self, provider: Provider, secret: str, model: str) -> Model: ...

    def embedder(self, provider: Provider, secret: str, model: str) -> EmbeddingModel: ...

    def bedrock_embedder(self, account: BedrockAccount, model: str) -> EmbeddingModel: ...

    def reranker(self, provider: Provider, secret: str, model: str) -> Reranker: ...
