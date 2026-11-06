"""The rule-driven fake injection classifier, for tests: it flags a text when it contains a
configured phrase, with that rule's label, score and reason."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.guardrails.classifier import InjectionFlag


@dataclass(frozen=True)
class FakeRule:
    # Flags texts containing this, ignoring case.
    contains: str
    label: str
    score: float
    reason: str


class RuleDrivenClassifier:
    """Flags a text with the first rule it matches. With no rules, nothing is flagged. Set
    ``failure`` to make classification raise it."""

    def __init__(self, rules: Sequence[FakeRule] = ()) -> None:
        self.rules = list(rules)
        self.failure: Exception | None = None

    def classify(self, texts: Sequence[str]) -> list[InjectionFlag | None]:
        if self.failure is not None:
            raise self.failure
        return [self._verdict(text) for text in texts]

    def _verdict(self, text: str) -> InjectionFlag | None:
        for rule in self.rules:
            if rule.contains.casefold() in text.casefold():
                return InjectionFlag(rule.label, rule.score, rule.reason)
        return None
