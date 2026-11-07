"""The Guardrail pipeline: the Agent runtime with the input Guardrail in front of it.

``GuardrailPipeline.run_turn`` takes exactly what ``app.runtime.runtime.run_turn`` takes and
streams the same events, so callers swap one for the other. Before the runtime sees the
Visitor's message, the input classifier (the injection-classifier port: the local ONNX model in
production, the rule-driven fake in tests) judges it. When it flags the message and the Agent's
input mode is block, the turn short-circuits: no retrieval, no model call, a ``RefusalEvent``
carrying the Agent's refusal text, then a ``DoneEvent`` whose answer is that text and whose
Guardrail outcome says why. In warn mode a flagged message is answered, but the runtime adds a
caution block to the prompt and the answer's ``DoneEvent`` carries an ``input / injection /
flagged`` outcome, so the Message is flagged. In log mode it is answered exactly as an unflagged
one would be, and the outcome (``logged``) only records the verdict. An unflagged message is
answered as usual and leaves no outcome (the canary filter still wraps every model stream).
"""

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

from pydantic_ai.models import Model

from app.agents.config import AgentConfig, InputMode
from app.core.settings import Settings
from app.guardrails import onnx_model
from app.guardrails.classifier import InjectionClassifier
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.heuristic import HeuristicClassifier
from app.guardrails.local import LocalClassifier
from app.guardrails.outcomes import GuardrailOutcome
from app.runtime.prompt import Turn
from app.runtime.runtime import DoneEvent, Retrieve, TurnEvent, run_turn


@dataclass(frozen=True)
class RefusalEvent:
    """The input Guardrail blocked the message: ``text`` (the Agent's refusal text) is the
    whole reply."""

    text: str


GuardedEvent = TurnEvent | RefusalEvent


def blocked(outcomes: Sequence[Mapping[str, object]]) -> bool:
    """Whether a saved answer's Guardrail outcomes say the input Guardrail blocked its
    question."""
    return any((o["layer"], o["action"]) == ("input", "blocked") for o in outcomes)


class GuardrailPipeline:
    def __init__(self, classifier: InjectionClassifier) -> None:
        # The input classifier, loaded once per process.
        self.classifier = classifier

    async def run_turn(
        self,
        turns: Sequence[Turn],
        config: AgentConfig,
        instructions: str,
        visitor_input: str,
        *,
        model: Model,
        retrieve: Retrieve,
    ) -> AsyncIterator[GuardedEvent]:
        guardrails = config.guardrails
        # Classification is CPU-bound (ONNX inference), so it runs off the event loop.
        (flag,) = await asyncio.to_thread(self.classifier.classify, [visitor_input])
        if flag is not None and guardrails.input_mode is InputMode.BLOCK:
            yield RefusalEvent(guardrails.refusal_text)
            yield DoneEvent(
                answer=guardrails.refusal_text,
                input_tokens=0,
                output_tokens=0,
                retrieved=[],
                excluded=[],
                refused=True,
                guardrail_outcomes=[
                    GuardrailOutcome("input", "injection", "blocked", flag.reason, flag.score)
                ],
            )
            return
        warned = flag is not None and guardrails.input_mode is InputMode.WARN
        async for event in run_turn(
            turns,
            config,
            instructions,
            visitor_input,
            model=model,
            retrieve=retrieve,
            cautioned=warned,
        ):
            if flag is not None and isinstance(event, DoneEvent):
                # Record the input verdict first, before what later layers decided.
                verdict = GuardrailOutcome(
                    "input", "injection", "flagged" if warned else "logged", flag.reason, flag.score
                )
                event = dataclasses.replace(
                    event, guardrail_outcomes=[verdict, *event.guardrail_outcomes]
                )
            yield event


def build_pipeline(settings: Settings) -> GuardrailPipeline:
    """The pipeline with the input classifier the settings choose. The local model loads on
    the first message it classifies."""
    classifier: InjectionClassifier
    if settings.input_classifier == "fake":
        classifier = RuleDrivenClassifier()
    elif settings.input_classifier == "heuristic":
        classifier = HeuristicClassifier()
    else:
        classifier = LocalClassifier(onnx_model.load, settings.input_classifier_threshold)
    return GuardrailPipeline(classifier)
