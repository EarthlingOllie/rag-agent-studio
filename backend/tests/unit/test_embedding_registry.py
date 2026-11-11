"""The Embedding Model registry: every model a Project can embed with, and what it needs."""

import pytest

from app.credentials.registry import PROVIDERS, Capability
from app.embeddings.registry import (
    DEFAULT_MODEL_ID,
    EMBEDDING_MODELS,
    LOCAL_MODEL,
    embedding_model,
)


def test_the_local_model_is_the_default_and_needs_no_credential() -> None:
    assert DEFAULT_MODEL_ID == "multilingual-e5-small"
    assert EMBEDDING_MODELS[DEFAULT_MODEL_ID] is LOCAL_MODEL
    assert (LOCAL_MODEL.provider, LOCAL_MODEL.dimension) == ("local", 384)
    assert LOCAL_MODEL.tokenizer == "intfloat/multilingual-e5-small"
    assert LOCAL_MODEL.required_capability is None


@pytest.mark.parametrize(
    ("model_id", "provider", "dimension", "tokenizer"),
    [
        ("text-embedding-3-small", "openai", 1536, "cl100k_base"),
        ("text-embedding-3-large", "openai", 3072, "cl100k_base"),
        ("voyage-3.5", "voyage", 1024, "voyageai/voyage-3.5"),
        ("voyage-3.5-lite", "voyage", 1024, "voyageai/voyage-3.5-lite"),
        ("voyage-multilingual-2", "voyage", 1024, "voyageai/voyage-multilingual-2"),
        ("amazon.titan-embed-text-v2:0", "bedrock", 1024, "amazon.titan-embed-text-v2"),
        (
            "cohere.embed-multilingual-v3",
            "bedrock",
            1024,
            "Cohere/Cohere-embed-multilingual-v3.0",
        ),
    ],
)
def test_each_provider_model_records_provider_dimension_and_tokenizer(
    model_id: str, provider: str, dimension: int, tokenizer: str
) -> None:
    model = embedding_model(model_id)

    assert (model.provider, model.dimension, model.tokenizer) == (provider, dimension, tokenizer)
    assert model.required_capability == "embeddings"
    assert model.max_tokens > 0


def test_every_embedding_model_a_provider_offers_is_in_the_registry() -> None:
    offered = {
        (model.id, spec.provider.value)
        for spec in PROVIDERS.values()
        for model in spec.models.get(Capability.EMBEDDINGS, ())
    }
    registered = {
        (model.id, model.provider)
        for model in EMBEDDING_MODELS.values()
        if model.provider != "local"
    }

    assert registered == offered


def test_an_unknown_model_is_not_in_the_registry() -> None:
    with pytest.raises(KeyError):
        embedding_model("no-such-model")
