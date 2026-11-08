"""The local injection classifier's windowing, maximum score and threshold, with a stubbed ONNX
session (the real model is exercised by the live suite).

The stub's "tokenizer" reads a text of numbers as their token IDs. The stub model reads token
99 as an attack: a window holding it scores about 0.982 (logits -2 and 2), any other 0.018."""

from collections.abc import Mapping, Sequence

import numpy as np
import pytest
from numpy.typing import NDArray

from app.core.settings import Settings
from app.guardrails.classifier import INJECTION_LABEL, InjectionClassifier, InjectionFlag
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.heuristic import HeuristicClassifier
from app.guardrails.local import LoadedModel, LocalClassifier, windows
from app.guardrails.pipeline import build_pipeline
from tests.conftest import TEST_LOCAL_KEY_WRAPPER_KEY

CLS, SEP, ATTACK = 1, 2, 99
INJECTION_PROBABILITY = round(float(1 / (1 + np.exp(-4))), 4)  # softmax of (-2, 2)


class StubSession:
    def __init__(self) -> None:
        self.inputs: list[list[int]] = []

    def run(
        self, output_names: None, input_feed: Mapping[str, NDArray[np.int64]]
    ) -> Sequence[NDArray[np.float32]]:
        (ids,) = input_feed["input_ids"].tolist()
        assert input_feed["attention_mask"].tolist() == [[1] * len(ids)]
        self.inputs.append(ids)
        # Class 0 is "safe", class 1 "injection".
        logits = [-2.0, 2.0] if ATTACK in ids else [2.0, -2.0]
        return [np.array([logits], dtype=np.float32)]


def numbers(text: str) -> list[int]:
    return [int(word) for word in text.split()]


def text(*ids: int) -> str:
    return " ".join(str(i) for i in ids)


def classifier(
    session: StubSession, *, max_tokens: int = 6, threshold: float = 0.5, overlap: int = 1
) -> LocalClassifier:
    model = LoadedModel(
        session=session,
        tokenize=numbers,
        cls_id=CLS,
        sep_id=SEP,
        injection_index=1,
        max_tokens=max_tokens,
    )
    return LocalClassifier(lambda: model, threshold=threshold, overlap=overlap)


def test_a_short_text_is_one_window_wrapped_in_the_models_special_tokens() -> None:
    session = StubSession()

    flags = classifier(session).classify([text(10, ATTACK), text(10, 11)])

    assert session.inputs == [[CLS, 10, ATTACK, SEP], [CLS, 10, 11, SEP]]
    assert flags == [
        InjectionFlag(
            INJECTION_LABEL,
            INJECTION_PROBABILITY,
            f"The local classifier scored the message {INJECTION_PROBABILITY:.2f} as a prompt "
            "injection.",
        ),
        None,
    ]
    assert INJECTION_PROBABILITY == 0.982


def test_the_reason_names_what_was_classified() -> None:
    model = LoadedModel(StubSession(), numbers, CLS, SEP, 1, 6)
    chunks = LocalClassifier(lambda: model, threshold=0.5, subject="Chunk")

    (flag,) = chunks.classify([text(ATTACK)])

    assert flag is not None
    assert flag.reason == "The local classifier scored the Chunk 0.98 as a prompt injection."


def test_a_long_text_is_split_into_overlapping_windows_that_cover_every_token() -> None:
    session = StubSession()
    # 4 tokens per window (6 less the two special tokens), overlapping by 1.
    benign = classifier(session).classify([text(*range(10, 20))])

    assert benign == [None]
    assert session.inputs == [
        [CLS, 10, 11, 12, 13, SEP],
        [CLS, 13, 14, 15, 16, SEP],
        [CLS, 16, 17, 18, 19, SEP],
    ]


@pytest.mark.parametrize("position", range(10))
def test_the_highest_window_score_wins_wherever_the_attack_is(position: int) -> None:
    ids = list(range(10, 20))
    ids[position] = ATTACK

    (flag,) = classifier(StubSession()).classify([text(*ids)])

    assert flag is not None
    assert flag.score == INJECTION_PROBABILITY


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (0, [[]]),
        (3, [[0, 1, 2]]),
        (4, [[0, 1, 2, 3]]),
        (5, [[0, 1, 2, 3], [3, 4]]),
        (7, [[0, 1, 2, 3], [3, 4, 5, 6]]),
        (8, [[0, 1, 2, 3], [3, 4, 5, 6], [6, 7]]),
    ],
)
def test_windows_cover_the_text_to_its_end_and_no_further(
    length: int, expected: list[list[int]]
) -> None:
    assert windows(list(range(length)), size=4, overlap=1) == expected


def test_an_empty_message_is_scored_as_the_special_tokens_alone() -> None:
    session = StubSession()

    assert classifier(session).classify([""]) == [None]
    assert session.inputs == [[CLS, SEP]]


def test_an_overlap_as_large_as_the_window_still_moves_forward() -> None:
    session = StubSession()

    classifier(session, max_tokens=4, overlap=64).classify([text(10, 11, 12, 13)])

    # 2 tokens per window; the overlap is capped at 1 so each window moves on by one token.
    assert session.inputs == [[CLS, 10, 11, SEP], [CLS, 11, 12, SEP], [CLS, 12, 13, SEP]]


def test_a_score_at_the_threshold_is_flagged_and_one_below_it_is_not() -> None:
    at = classifier(StubSession(), threshold=INJECTION_PROBABILITY)
    above = classifier(StubSession(), threshold=0.99)

    assert at.classify([text(ATTACK)])[0] is not None
    assert above.classify([text(ATTACK)]) == [None]


def test_the_model_is_loaded_once_on_first_use() -> None:
    session = StubSession()
    loads: list[int] = []

    def load() -> LoadedModel:
        loads.append(1)
        return LoadedModel(session, numbers, CLS, SEP, 1, 6)

    local = LocalClassifier(load, threshold=0.5)
    assert loads == []

    local.classify([text(10)])
    local.classify([text(11), text(12)])

    assert loads == [1]
    assert local.score(text(ATTACK)) == pytest.approx(0.982, abs=1e-3)


def test_the_settings_choose_the_input_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INPUT_CLASSIFIER", raising=False)

    def pipeline(**values: str) -> InjectionClassifier:
        settings = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            redis_url="redis://localhost:6379/0",
            local_key_wrapper_key=TEST_LOCAL_KEY_WRAPPER_KEY,
            **values,  # type: ignore[arg-type]
        )
        return build_pipeline(settings).classifier

    # Production checks messages with the local model (loaded on first use, so not here).
    local = pipeline()
    assert isinstance(local, LocalClassifier)
    assert local.threshold == 0.5
    tuned = pipeline(input_classifier_threshold="0.8")
    assert isinstance(tuned, LocalClassifier)
    assert tuned.threshold == 0.8
    assert isinstance(pipeline(input_classifier="heuristic"), HeuristicClassifier)
    assert isinstance(pipeline(input_classifier="fake"), RuleDrivenClassifier)
