"""Guardrail outcomes: what each Guardrail layer decided about one answer, saved on the Message
and shown in its Trace."""

from dataclasses import asdict, dataclass
from typing import Literal

# ``input``: the input Guardrail, which checks the Visitor's message before the model sees it.
# ``canary``: the Canary token, which checks the answer as it streams.
Layer = Literal["input", "canary"]
Verdict = Literal["injection", "leak"]
Action = Literal["blocked", "replaced", "flagged"]


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
