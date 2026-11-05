"""Live suite: the local Embedding Model (multilingual-e5-small through fastembed) and its
tokenizer, downloaded from Hugging Face on first use. Run with ``make test-live``. Skipped with
the reason when the model can't be had, unless ``LIVE_REQUIRE_MODELS=1``."""

import math

import pytest

from app.embeddings.local import LocalEmbedder
from tests.live.models import LOCAL_EMBEDDING_MODEL, require_models

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _model_available() -> None:
    require_models(LOCAL_EMBEDDING_MODEL)


def test_the_local_model_embeds_passages_into_unit_vectors_of_its_dimension() -> None:
    embedder = LocalEmbedder()

    first, second, unrelated = embedder.embed_passages(
        [
            "Everyone gets 25 days of annual leave.",
            "Staff have 25 days of holiday a year.",
            "Claim expenses within 30 days.",
        ]
    )

    assert len(first) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, rel_tol=1e-4)

    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(first, second) > cosine(first, unrelated)


def test_the_chunker_counts_tokens_with_the_models_own_tokenizer() -> None:
    tokenizer = LocalEmbedder().tokenizer(max_tokens=256)

    assert tokenizer.get_max_tokens() == 256
    # XLM-RoBERTa's sentencepiece splits words into more than one token each.
    assert tokenizer.count_tokens("Everyone gets annual leave") >= 4
