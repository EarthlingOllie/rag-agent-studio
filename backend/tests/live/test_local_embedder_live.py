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


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_the_local_model_embeds_passages_into_unit_vectors_of_its_dimension() -> None:
    embedder = LocalEmbedder()

    first, second, unrelated = await embedder.embed_passages(
        [
            "Everyone gets 25 days of annual leave.",
            "Staff have 25 days of holiday a year.",
            "Claim expenses within 30 days.",
        ]
    )

    assert len(first) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, rel_tol=1e-4)

    assert _cosine(first, second) > _cosine(first, unrelated)


async def test_a_query_is_nearest_the_passage_that_answers_it() -> None:
    # multilingual-e5-small is small: a paraphrase with no shared words ("How much holiday do I
    # get?") scores the expenses passage slightly higher (0.805 against 0.796, the same as the
    # model's own transformers implementation gives). So each query shares the topic's words.
    embedder = LocalEmbedder()
    leave, expenses = await embedder.embed_passages(
        ["Everyone gets 25 days of annual leave.", "Claim expenses within 30 days."]
    )

    leave_query = await embedder.embed_query("How many days of annual leave do I get?")
    expenses_query = await embedder.embed_query("How long do I have to claim expenses?")

    assert len(leave_query) == 384
    assert _cosine(leave_query, leave) > _cosine(leave_query, expenses)
    assert _cosine(expenses_query, expenses) > _cosine(expenses_query, leave)


def test_the_chunker_counts_tokens_with_the_models_own_tokenizer() -> None:
    tokenizer = LocalEmbedder().tokenizer(max_tokens=256)

    assert tokenizer.get_max_tokens() == 256
    # XLM-RoBERTa's sentencepiece splits words into more than one token each.
    assert tokenizer.count_tokens("Everyone gets annual leave") >= 4
