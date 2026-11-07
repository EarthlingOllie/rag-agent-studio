"""The Guardrail pipeline: the Agent runtime with the input Guardrail in front of it.

``GuardrailPipeline.run_turn`` takes exactly what ``app.runtime.runtime.run_turn`` takes and
streams the same events, so callers swap one for the other. Before the runtime sees the
Visitor's message, the input classifier (the injection-classifier port: the local ONNX model in
production, the rule-driven fake in tests) judges it. When it flags the message and the Agent's
input mode is block, the turn short-circuits: no retrieval, no model call, a ``RefusalEvent``
carrying the Agent's refusal text, then a ``DoneEvent`` whose answer is that text and whose
Guardrail outcome says why. When the Agent names an LLM classifier, a message the local
classifier passed is judged by it too; when it can't judge (its provider failed), the Agent's
fail mode decides: closed treats the message as flagged, open answers it and records that it
went unchecked. Otherwise the runtime answers as usual (the canary filter still
wraps its stream). Warn and log modes are ticket 08-02's; until then a flagged message in
those modes is answered as usual.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from pydantic_ai.models import Model

from app.agents.config import AgentConfig, FailMode, InputMode
from app.core.settings import Settings
from app.guardrails import onnx_model
from app.guardrails.classifier import InjectionClassifier
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.heuristic import HeuristicClassifier
from app.guardrails.llm import LlmClassifier, LlmClassifierError
from app.guardrails.local import LocalClassifier
from app.guardrails.outcomes import GuardrailOutcome
from app.runtime.errors import ProviderErrorKind
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


_WHY: dict[str, str] = {
    ProviderErrorKind.INVALID_KEY: "the provider rejected the API key",
    ProviderErrorKind.RATE_LIMITED: "the provider says the key is over its rate limit or quota",
    ProviderErrorKind.MODEL_UNAVAILABLE: "the model isn't available from the provider",
    ProviderErrorKind.PROVIDER_ERROR: "the provider failed",
}


def _failed(classifier: LlmClassifier, error: LlmClassifierError, *, closed: bool) -> str:
    """The reason an Editor reads in the Trace when the LLM classifier couldn't judge."""
    why = (
        f"it didn't answer within {classifier.timeout_s:g} s"
        if error.kind == "timeout"
        else _WHY[error.kind]
    )
    then = (
        "The Agent fails closed, so the message was refused."
        if closed
        else "The Agent fails open, so the message was answered without this check."
    )
    return f"The LLM classifier ({classifier.model_name}) couldn't check the message: {why}. {then}"


class GuardrailPipeline:
    def __init__(
        self, classifier: InjectionClassifier, llm_classifier_timeout_s: float = 10
    ) -> None:
        # The input classifier, loaded once per process.
        self.classifier = classifier
        # How long the LLM classifier may take before it counts as a provider error.
        self.llm_classifier_timeout_s = llm_classifier_timeout_s

    def llm_classifier(self, build: Callable[[], Model], model_name: str) -> LlmClassifier:
        """An Agent's LLM classifier: the chat model ``build`` returns, named ``model_name``."""
        return LlmClassifier(build, model_name, self.llm_classifier_timeout_s)

    async def run_turn(
        self,
        turns: Sequence[Turn],
        config: AgentConfig,
        instructions: str,
        visitor_input: str,
        *,
        model: Model,
        retrieve: Retrieve,
        llm_classifier: LlmClassifier | None = None,
    ) -> AsyncIterator[GuardedEvent]:
        guardrails = config.guardrails
        # Classification is CPU-bound (ONNX inference), so it runs off the event loop.
        (flag,) = await asyncio.to_thread(self.classifier.classify, [visitor_input])
        outcome: GuardrailOutcome | None = None
        # The LLM classifier's failure, when the Agent fails open: recorded on the answer.
        unchecked: GuardrailOutcome | None = None
        if flag is None and llm_classifier is not None:
            try:
                flag = await llm_classifier.classify(visitor_input)
            except LlmClassifierError as error:
                if guardrails.fail_mode is FailMode.CLOSED:
                    outcome = GuardrailOutcome(
                        "input", "unchecked", "blocked", _failed(llm_classifier, error, closed=True)
                    )
                else:
                    unchecked = GuardrailOutcome(
                        "input",
                        "unchecked",
                        "allowed",
                        _failed(llm_classifier, error, closed=False),
                    )
        if flag is not None:
            outcome = GuardrailOutcome("input", "injection", "blocked", flag.reason, flag.score)
        if outcome is not None and guardrails.input_mode is InputMode.BLOCK:
            yield RefusalEvent(guardrails.refusal_text)
            yield DoneEvent(
                answer=guardrails.refusal_text,
                input_tokens=0,
                output_tokens=0,
                retrieved=[],
                excluded=[],
                refused=True,
                guardrail_outcomes=[outcome],
            )
            return
        async for event in run_turn(
            turns, config, instructions, visitor_input, model=model, retrieve=retrieve
        ):
            if isinstance(event, DoneEvent) and unchecked is not None:
                event = replace(event, guardrail_outcomes=[unchecked, *event.guardrail_outcomes])
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
    return GuardrailPipeline(classifier, settings.llm_classifier_timeout_s)
