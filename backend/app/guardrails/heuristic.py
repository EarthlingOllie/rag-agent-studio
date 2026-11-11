"""The heuristic injection classifier: the ingestion scan's baseline until spec 08's ONNX
classifier.

A handful of patterns catch the common shapes of an indirect prompt injection: telling the AI
to ignore its instructions, asking for its system prompt, chat-model control markup, giving it a
new role, addressing the text to an AI, and asking it to hide something from the user. Each
pattern has a score; several matching raise the combined score (``1 - Π(1 - score)``). The
reason names every pattern that matched, quoting the words that matched it.

Text is NFKC-normalised (folding fullwidth and other lookalike letters) and its whitespace
collapsed first, so line breaks and lookalikes don't hide a phrase.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.guardrails.classifier import INJECTION_LABEL, InjectionFlag

_AI = r"(?:ai assistants?|ai models?|ai|a\.i\.|llms?|chatbots?|language models?|assistants?)"


@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    score: float
    # Completed by the quoted match: 'Tells the AI to ignore its instructions ("…").'
    description: str


def _pattern(regex: str, score: float, description: str) -> _Pattern:
    return _Pattern(re.compile(regex, re.IGNORECASE), score, description)


# Strongest first: the reason lists the patterns in this order.
PATTERNS = (
    _pattern(
        r"\b(?:ignore|disregard|forget|override|bypass)\b(?: \w+){0,3}? "
        r"(?:instructions?|prompts?|rules|guidelines|directions|guardrails)\b",
        0.9,
        "Tells the AI to ignore its instructions",
    ),
    _pattern(
        r"\b(?:reveal|print|show|repeat|output|leak|disclose)\b(?: \w+){0,3}? "
        r"(?:system prompt|(?:hidden|initial|original|secret) (?:prompt|instructions))\b",
        0.85,
        "Asks the AI to reveal its system prompt",
    ),
    _pattern(
        r"<\|im_start\|>|<\|system\|>|\[/?INST\]|<</?SYS>>|</?system>",
        0.8,
        "Contains chat-model control markup",
    ),
    _pattern(
        r"\b(?:you are now|from now on,? you|pretend (?:to be|you are)|"
        r"act as (?:an? )?(?:unrestricted|unfiltered|jailbroken|different))\b",
        0.7,
        "Tries to give the AI a new role",
    ),
    _pattern(
        rf"\b(?:(?:attention|note|message|instructions?) (?:to|for) (?:all |any )?{_AI}|"
        rf"if you are an? {_AI})(?!\w)",
        0.7,
        "Addresses the text to an AI",
    ),
    _pattern(
        r"\b(?:do not|don't|never)\b (?:tell|mention|reveal|inform|show|disclose)\b"
        r"[^.]{0,40}?\b(?:users?|readers?|visitors?|humans?)\b",
        0.6,
        "Asks the AI to hide something from the user",
    ),
)


def _normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


class HeuristicClassifier:
    """Flags text matching any of ``PATTERNS``."""

    def classify(self, texts: Sequence[str]) -> list[InjectionFlag | None]:
        return [self._classify(text) for text in texts]

    def _classify(self, text: str) -> InjectionFlag | None:
        normalised = _normalise(text)
        matches = [
            (pattern, match)
            for pattern in PATTERNS
            if (match := pattern.regex.search(normalised)) is not None
        ]
        if not matches:
            return None
        benign = 1.0
        for pattern, _ in matches:
            benign *= 1 - pattern.score
        reason = " ".join(
            f'{pattern.description} ("{match.group(0)}").' for pattern, match in matches
        )
        return InjectionFlag(INJECTION_LABEL, round(1 - benign, 2), reason)
