"""Provider Embedding Models (Voyage, OpenAI, Bedrock) behind the embedder port.

A provider model is called through the model gateway with the Project's Provider Credential;
the gateway refuses a model the credential doesn't offer, and its fake adapters stand in for
the providers in tests and ``docker compose``.

Chunks are sized with ``ApproximateTokenizer``: providers' tokenizers aren't all published, and
fetching the ones that are would need a download at runtime. Counting one token per
``CHARS_PER_TOKEN`` characters over-counts for English and most European languages, so a Chunk
stays inside the model's limit.
"""

import math
from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from pydantic_ai.embeddings import EmbeddingModel as GatewayEmbeddingModel

from app.credentials.models import ProviderCredential
from app.embeddings.port import Embedder
from app.embeddings.registry import EmbeddingModel
from app.gateway.gateway import ModelGateway

CHARS_PER_TOKEN = 3


class ApproximateTokenizer(BaseTokenizer):
    """Counts one token per ``CHARS_PER_TOKEN`` characters, rounded up."""

    max_tokens: int

    def count_tokens(self, text: str) -> int:
        return math.ceil(len(text) / CHARS_PER_TOKEN)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        return self.count_tokens


class EmbeddingSizeError(Exception):
    """The provider answered with vectors of another size than the model's registered one."""


class ProviderEmbedder:
    """One provider Embedding Model, through the gateway's client for the Project's credential."""

    def __init__(self, model: EmbeddingModel, client: GatewayEmbeddingModel) -> None:
        self._model = model
        self._client = client

    @property
    def model(self) -> EmbeddingModel:
        return self._model

    def tokenizer(self, max_tokens: int) -> BaseTokenizer:
        return ApproximateTokenizer(max_tokens=max_tokens)

    def _checked(self, vectors: list[list[float]]) -> list[list[float]]:
        for vector in vectors:
            if len(vector) != self._model.dimension:
                raise EmbeddingSizeError(
                    f"{self._model.id} answered with {len(vector)} dimensions, "
                    f"not {self._model.dimension}."
                )
        return vectors

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        result = await self._client.embed(texts, input_type="document")
        return self._checked([list(vector) for vector in result.embeddings])

    async def embed_query(self, text: str) -> list[float]:
        result = await self._client.embed(text, input_type="query")
        (vector,) = self._checked([list(vector) for vector in result.embeddings])
        return vector


def resolve_embedder(
    model: EmbeddingModel,
    credential: ProviderCredential | None,
    local: dict[str, Embedder],
    gateway: ModelGateway,
) -> Embedder:
    """The embedder for a Project's Embedding Model: the local one, or the provider model
    through the gateway with the Project's credential. Raises the gateway's errors when the
    credential can't make the call."""
    if model.is_local:
        return local[model.id]
    # A provider model is only ever chosen with its credential (enforced when it is chosen).
    assert credential is not None  # noqa: S101
    return ProviderEmbedder(model, gateway.embedder(credential, model.id))
