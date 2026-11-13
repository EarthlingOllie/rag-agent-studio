"""The Guardrail pipeline: the Agent runtime with the input Guardrail in front of it.

``GuardrailPipeline.run_turn`` takes exactly what ``app.runtime.runtime.run_turn`` takes and
streams the same events, so callers swap one for the other. Before the runtime sees the
Visitor's message, the input classifier (the injection-classifier port: the local ONNX model in
production, the rule-driven fake in tests) judges it, alone and read together with the
Conversation's last remembered questions, so an attack split across turns is judged whole.
When it flags the message, the turn short-circuits: no retrieval, no model call, a
``RefusalEvent`` carrying the Agent's refusal text, then a ``DoneEvent`` whose answer is that
text and whose Guardrail outcome says why. A detected injection is always refused: no setting
lets it into the model's context (the old warn and log input modes are gone, and an
``input_mode`` stored with an Agent is ignored). An unflagged message is answered as usual and
leaves no outcome (the canary filter still wraps every model stream).

When the Agent names an LLM classifier, a message the local classifier passed is judged by it
too; when it can't judge (its provider failed), the Agent's fail mode decides: closed treats
the message as flagged, open answers it and records that it went unchecked.
"""

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass

from pydantic_ai.models import Model

from app.agents.config import AgentConfig, FailMode
from app.core.settings import Settings
from app.guardrails import onnx_model
from app.guardrails.classifier import InjectionClassifier, InjectionFlag
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
        flag = await self._judge(turns, visitor_input)
        outcome: GuardrailOutcome | None = None
        # The LLM classifier's failure, when the Agent fails open: recorded on the answer.
        unchecked: GuardrailOutcome | None = None
        if flag is None and llm_classifier is not None:
            try:
                flag = await llm_classifier.classify(_window(turns, visitor_input))
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
        # A detected injection is always refused: no setting lets it into the model's context.
        if outcome is not None:
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
                # Record the input verdict first, before what later layers decided.
                event = dataclasses.replace(
                    event, guardrail_outcomes=[unchecked, *event.guardrail_outcomes]
                )
            yield event

    async def _judge(self, turns: Sequence[Turn], visitor_input: str) -> InjectionFlag | None:
        """The local classifier's verdict on the message. It judges the message alone and,
        when there are remembered questions, the message read together with the last of them,
        so an attack split across turns is caught as a whole. Either flag counts against the
        message."""
        texts = [visitor_input]
        if turns:
            texts.append(_window(turns, visitor_input))
        # Classification is CPU-bound (ONNX inference), so it runs off the event loop.
        flags = await asyncio.to_thread(self.classifier.classify, texts)
        return next((flag for flag in flags if flag is not None), None)


# How many remembered questions are judged with the Visitor's message.
WINDOW_TURNS = 3


def _window(turns: Sequence[Turn], visitor_input: str) -> str:
    """The Visitor's message after the last ``WINDOW_TURNS`` remembered questions, in order and
    run together as one text, as the model reads the Conversation: what the input classifiers
    judge. With no remembered questions, the message alone."""
    recent = [turn.question for turn in list(turns)[-WINDOW_TURNS:]]
    return " ".join([*recent, visitor_input])


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
