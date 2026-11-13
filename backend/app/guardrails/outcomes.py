"""Guardrail outcomes: what each Guardrail layer decided about one answer, saved on the Message
and shown in its Trace."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

# ``input``: the input Guardrail, which checks the Visitor's message before the model sees it.
# ``canary``: the Canary token, which checks the answer as it streams.
Layer = Literal["input", "canary"]
# ``unchecked``: the LLM classifier couldn't judge the message (its provider failed); the
# Agent's fail mode decides between ``blocked`` (closed) and ``allowed`` (open).
Verdict = Literal["injection", "leak", "unchecked"]
# ``blocked``: the input Guardrail refused the message (block mode). ``flagged``: the message or
# answer went through but is marked (the input Guardrail's warn mode, which also cautions the
# model; or an encoded canary found after sending). ``logged``: the input Guardrail's verdict is
# only recorded (log mode). ``replaced``: the canary cut the answer off and replaced it.
# ``allowed``: the LLM classifier couldn't check the message and the Agent fails open.
Action = Literal["blocked", "replaced", "flagged", "logged", "allowed"]


@dataclass(frozen=True)
class GuardrailOutcome:
    layer: Layer
    verdict: Verdict
    action: Action
    reason: str
    # How sure the layer was, from 0 to 1, when it scores (the injection classifier does).
    score: float | None = None

    def as_dict(self) -> dict[str, str | float | None]:
        return asdict(self)


def blocked(outcomes: Sequence[Mapping[str, object]]) -> bool:
    """Whether a saved answer's Guardrail outcomes say the input Guardrail blocked its
    question."""
    return any((o["layer"], o["action"]) == ("input", "blocked") for o in outcomes)


def judged_injection(outcomes: Sequence[Mapping[str, object]]) -> bool:
    """Whether a saved answer's Guardrail outcomes say the input Guardrail judged its question
    an injection, or refused it unchecked: blocked, or answered under the old warn or log
    modes (``flagged``, ``logged``). Such a question is never replayed to the model."""
    return blocked(outcomes) or any(
        (o["layer"], o["verdict"]) == ("input", "injection") for o in outcomes
    )
