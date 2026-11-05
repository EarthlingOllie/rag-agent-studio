"""The Embedding Model registry: every model a Project can embed its Chunks with.

Each entry gives the provider, the vector dimension (Chunks store vectors of that size, with
an HNSW index per model), the tokenizer the chunker counts tokens with, and the token limit.
Provider models (Voyage, OpenAI, Bedrock) join in ticket 03-09 through the model gateway.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingModel:
    id: str
    provider: str
    dimension: int
    # The Hugging Face tokenizer the chunker counts tokens with, so Chunks fit the model.
    tokenizer: str
    max_tokens: int
    # e5 models expect these prefixes on what they embed.
    query_prefix: str = ""
    passage_prefix: str = ""


LOCAL_MODEL = EmbeddingModel(
    id="multilingual-e5-small",
    provider="local",
    dimension=384,
    tokenizer="intfloat/multilingual-e5-small",
    max_tokens=512,
    query_prefix="query: ",
    passage_prefix="passage: ",
)

DEFAULT_MODEL_ID = LOCAL_MODEL.id

EMBEDDING_MODELS: dict[str, EmbeddingModel] = {LOCAL_MODEL.id: LOCAL_MODEL}
