"""The Embedding Model registry: every model a Project can embed its Chunks with.

Each entry gives the provider, the vector dimension (Chunks store vectors of that size, with
an HNSW index per model), the tokenizer the model reads text with, the token limit, and the
Provider Credential capability it needs.

- The local model (``multilingual-e5-small`` through fastembed) needs no credential; the
  chunker counts tokens with its Hugging Face tokenizer.
- Provider models (Voyage, OpenAI, Bedrock) are called through the model gateway with an
  ``embeddings`` credential. ``tokenizer`` names the provider's documented tokenizer; the
  chunker counts tokens with a conservative approximation of it (``app.embeddings.provider``),
  so no tokenizer download is needed and a Chunk never runs over the model's limit.
"""

from dataclasses import dataclass

LOCAL_PROVIDER = "local"
EMBEDDINGS_CAPABILITY = "embeddings"


@dataclass(frozen=True)
class EmbeddingModel:
    id: str
    provider: str
    dimension: int
    tokenizer: str
    max_tokens: int
    name: str = ""
    # e5 models expect these prefixes on what they embed.
    query_prefix: str = ""
    passage_prefix: str = ""
    # The Provider Credential capability needed to use the model; None for the local model.
    required_capability: str | None = EMBEDDINGS_CAPABILITY

    @property
    def is_local(self) -> bool:
        return self.provider == LOCAL_PROVIDER


LOCAL_MODEL = EmbeddingModel(
    id="multilingual-e5-small",
    name="multilingual-e5-small (built in)",
    provider=LOCAL_PROVIDER,
    dimension=384,
    tokenizer="intfloat/multilingual-e5-small",
    max_tokens=512,
    query_prefix="query: ",
    passage_prefix="passage: ",
    required_capability=None,
)

DEFAULT_MODEL_ID = LOCAL_MODEL.id

_PROVIDER_MODELS = (
    EmbeddingModel(
        "text-embedding-3-small", "openai", 1536, "cl100k_base", 8191, "text-embedding-3-small"
    ),
    EmbeddingModel(
        "text-embedding-3-large", "openai", 3072, "cl100k_base", 8191, "text-embedding-3-large"
    ),
    EmbeddingModel("voyage-3.5", "voyage", 1024, "voyageai/voyage-3.5", 32000, "voyage-3.5"),
    EmbeddingModel(
        "voyage-3.5-lite", "voyage", 1024, "voyageai/voyage-3.5-lite", 32000, "voyage-3.5-lite"
    ),
    EmbeddingModel(
        "voyage-multilingual-2",
        "voyage",
        1024,
        "voyageai/voyage-multilingual-2",
        32000,
        "voyage-multilingual-2",
    ),
    EmbeddingModel(
        "amazon.titan-embed-text-v2:0",
        "bedrock",
        1024,
        "amazon.titan-embed-text-v2",
        8192,
        "Titan Text Embeddings V2",
    ),
    EmbeddingModel(
        "cohere.embed-multilingual-v3",
        "bedrock",
        1024,
        "Cohere/Cohere-embed-multilingual-v3.0",
        512,
        "Cohere Embed Multilingual v3",
    ),
)

EMBEDDING_MODELS: dict[str, EmbeddingModel] = {
    model.id: model for model in (LOCAL_MODEL, *_PROVIDER_MODELS)
}


def embedding_model(model_id: str) -> EmbeddingModel:
    """The registered model; ``KeyError`` for an unknown ID."""
    return EMBEDDING_MODELS[model_id]
