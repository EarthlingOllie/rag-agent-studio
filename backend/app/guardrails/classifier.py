"""The injection-classifier port: does a text look like instructions aimed at an AI?

Ingestion runs every Chunk through it (the ingestion Guardrail scan) and stores the verdict of
each Chunk it flags; the input Guardrail runs every Visitor message through it. The local ONNX
classifier is the default adapter for both; the heuristic one is the baseline for stacks built
without the model.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

INJECTION_LABEL = "prompt_injection"


@dataclass(frozen=True)
class InjectionFlag:
    """Why the classifier flagged a text."""

    # What the classifier thinks the text is, such as ``prompt_injection``.
    label: str
    # How sure it is, from 0 to 1.
    score: float
    # A sentence an Editor can read: what in the text looks like instructions to an AI.
    reason: str


class InjectionClassifier(Protocol):
    def classify(self, texts: Sequence[str]) -> list[InjectionFlag | None]:
        """One verdict per text, in order: a flag, or ``None`` when the text looks benign."""
        ...
