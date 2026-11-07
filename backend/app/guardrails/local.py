"""The local injection classifier: a small ONNX prompt-injection model run on the CPU.

The model (``app.guardrails.onnx_model``: a DeBERTa-v3 prompt-injection classifier) reads at
most ``max_tokens`` tokens, its own special tokens included. A longer text is split into
windows that overlap by ``overlap`` tokens, so an attack straddling a boundary is whole in one
of them; each window is scored and the text's score is the highest. A text scoring at or above
the threshold is flagged.

The model is loaded the first time a text is classified. ``onnx_model.load`` caches it, so the
input Guardrail and the ingestion scan share one copy per process.
"""

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from app.guardrails.classifier import INJECTION_LABEL, InjectionFlag

REASON = "The local classifier scored the {subject} {score:.2f} as a prompt injection."


class Session(Protocol):
    """What the classifier needs of an ONNX Runtime ``InferenceSession``."""

    def run(
        self, output_names: None, input_feed: Mapping[str, NDArray[np.int64]]
    ) -> Sequence[NDArray[np.float32]]: ...


@dataclass(frozen=True)
class LoadedModel:
    session: Session
    # The text's token IDs, without the model's special tokens.
    tokenize: Callable[[str], list[int]]
    # The special tokens each window starts and ends with.
    cls_id: int
    sep_id: int
    # Which of the model's output classes means "prompt injection".
    injection_index: int
    # The most tokens the model reads at once, special tokens included.
    max_tokens: int


def windows(ids: list[int], size: int, overlap: int) -> list[list[int]]:
    """``ids`` cut into windows of at most ``size`` tokens, each overlapping the one before by
    ``overlap`` tokens. An empty text is one empty window."""
    step = size - overlap
    return [ids[start : start + size] for start in range(0, max(len(ids) - overlap, 1), step)]


class LocalClassifier:
    def __init__(
        self,
        load: Callable[[], LoadedModel],
        threshold: float,
        overlap: int = 64,
        *,
        subject: str = "message",
    ) -> None:
        self._load = load
        self._model: LoadedModel | None = None
        self._lock = threading.Lock()
        self.threshold = threshold
        self.overlap = overlap
        # What a flag's reason says was classified: the input Guardrail's "message", the
        # ingestion scan's "Chunk".
        self.subject = subject

    def _loaded(self) -> LoadedModel:
        with self._lock:
            if self._model is None:
                self._model = self._load()
            return self._model

    def _injection_probability(self, model: LoadedModel, window: list[int]) -> float:
        ids = np.array([[model.cls_id, *window, model.sep_id]], dtype=np.int64)
        (logits,) = model.session.run(None, {"input_ids": ids, "attention_mask": np.ones_like(ids)})
        row = logits[0].astype(np.float64)
        exp = np.exp(row - row.max())
        return float(exp[model.injection_index] / exp.sum())

    def score(self, text: str) -> float:
        """The highest probability, over the text's windows, that it is a prompt injection."""
        model = self._loaded()
        size = model.max_tokens - 2
        return max(
            self._injection_probability(model, window)
            for window in windows(model.tokenize(text), size, min(self.overlap, size - 1))
        )

    def classify(self, texts: Sequence[str]) -> list[InjectionFlag | None]:
        flags: list[InjectionFlag | None] = []
        for text in texts:
            score = round(self.score(text), 4)
            flags.append(
                InjectionFlag(
                    INJECTION_LABEL, score, REASON.format(subject=self.subject, score=score)
                )
                if score >= self.threshold
                else None
            )
        return flags
