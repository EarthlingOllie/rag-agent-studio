"""Guardrail outcomes: what each Guardrail layer decided about one answer, saved on the Message
and shown in its Trace."""

from dataclasses import asdict, dataclass
from typing import Literal

Layer = Literal["canary"]
Verdict = Literal["leak"]
Action = Literal["replaced", "flagged"]


@dataclass(frozen=True)
class GuardrailOutcome:
    layer: Layer
    verdict: Verdict
    action: Action
    reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)
