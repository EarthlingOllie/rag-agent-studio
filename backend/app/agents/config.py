"""AgentConfig: everything that shapes how an Agent answers, as one Pydantic model.

It is stored as ``jsonb`` on the Agent's Draft and validated on every read and write. Four
groups: Behaviour, Retrieval, Experience and Guardrails. New settings arrive as new fields with
defaults, so stored Drafts stay valid. Operational Settings and the Theme are not part of it
(ADR-0009).

This model checks shapes and ranges. Whether a credential offers a model, and whether a Tag is
in the Agent's Project, needs the database: ``app.agents.validation`` checks those on save.
"""

import enum
import uuid
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    UrlConstraints,
    model_validator,
)

SYSTEM_PROMPT_MAX = 20_000
FALLBACK_TEXT_MAX = 2_000
TOP_K_MAX = 20
DEFAULT_FALLBACK_TEXT = "Sorry, I don't know the answer to that."
MAX_OUTPUT_TOKENS_MAX = 8_192
REMEMBERED_TURNS_MAX = 20
TAGS_MAX = 50
DISPLAY_NAME_MAX = 100
GREETING_MAX = 1_000
STARTER_QUESTIONS_MAX = 6
SHORT_TEXT_MAX = 200
RATING_PROMPT_AFTER_MAX = 50
REFUSAL_TEXT_MAX = 2_000
SEARCH_LIMIT_MAX = 5
DEFAULT_REFUSAL_TEXT = "Sorry, I can't help with that request."

# Unknown settings are refused. In responses every field is present, so the generated client
# types a saved AgentConfig as complete while requests may leave fields to their defaults.
# NaN and Infinity, which Python's JSON parser accepts, are refused as not finite (AGT-F6).
_STRICT = ConfigDict(
    extra="forbid", json_schema_serialization_defaults_required=True, allow_inf_nan=False
)

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SHORT_TEXT_MAX)
]
HttpsUrl = Annotated[AnyUrl, UrlConstraints(max_length=2048, allowed_schemes=["https"])]


def _unique[T](items: list[T]) -> list[T]:
    return list(dict.fromkeys(items))


class ModelChoice(BaseModel):
    """A Provider Credential and one of its models. Saving checks the credential offers it."""

    model_config = _STRICT

    credential_id: uuid.UUID
    model: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Behaviour(BaseModel):
    model_config = _STRICT

    system_prompt: str = Field(default="", max_length=SYSTEM_PROMPT_MAX)
    # The Model override: a chat model of a chat-capable credential. None follows the
    # Organisation's Default Model.
    model: ModelChoice | None = None
    temperature: float = Field(default=0.7, ge=0, le=1)
    max_output_tokens: int = Field(default=1024, ge=1, le=MAX_OUTPUT_TOKENS_MAX)
    # How many earlier question-and-answer pairs of the Conversation the model is given.
    remembered_turns: int = Field(default=5, ge=0, le=REMEMBERED_TURNS_MAX)
    # The reply when retrieval finds no Chunk at or above the minimum score; the model isn't asked.
    fallback_text: str = Field(
        default=DEFAULT_FALLBACK_TEXT, min_length=1, max_length=FALLBACK_TEXT_MAX
    )


class RetrievalMode(enum.StrEnum):
    """How an Agent gets Chunks for a reply (ADR-0015). Automatic runs one Hybrid search on the
    Visitor input before the model is asked; Agentic gives the model Knowledge Search, its one
    tool, and lets it decide whether, how often and with what query to search."""

    AUTOMATIC = "automatic"
    AGENTIC = "agentic"


class Retrieval(BaseModel):
    model_config = _STRICT

    # How many Chunks are given to the model with each question.
    top_k: int = Field(default=5, ge=1, le=TOP_K_MAX)
    # The hybrid weighting: semantic search's share of the fused score, keyword search having
    # the rest. 1 is semantic search alone, 0 keyword search alone.
    hybrid_weight: float = Field(default=0.5, ge=0, le=1)
    # The minimum score: the relevance (0 to 1) a Chunk needs to be given to the model.
    min_score: float = Field(default=0, ge=0, le=1)
    # Tag scoping: only Documents with one of these Tags are searched. Empty searches them all.
    tag_ids: Annotated[list[uuid.UUID], AfterValidator(_unique)] = Field(
        default_factory=list, max_length=TAGS_MAX
    )
    # A rerank model of a rerank-capable credential, or None for no Reranker.
    reranker: ModelChoice | None = None
    # Whether Visitors see the citations of an answer.
    citations: bool = True
    # The Retrieval Mode: Agentic for a new Agent, the more accurate of the two (spec 13).
    mode: RetrievalMode = RetrievalMode.AGENTIC
    # The Search limit: the most Searches an Agentic reply may make. Ignored when Automatic.
    search_limit: int = Field(default=3, ge=1, le=SEARCH_LIMIT_MAX)


class UiText(BaseModel):
    """Overrides of the widget's built-in text. None keeps the built-in text."""

    model_config = _STRICT

    send_button: ShortText | None = None
    rate_conversation: ShortText | None = None
    unavailable_message: ShortText | None = None
    # Shown to Visitors while an Agentic Agent searches; None keeps "Searching the knowledge base…".
    searching_status: ShortText | None = None


class Experience(BaseModel):
    model_config = _STRICT

    # The name Visitors see. Empty shows the Agent's name.
    display_name: str = Field(default="", max_length=DISPLAY_NAME_MAX)
    avatar_url: HttpsUrl | None = None
    greeting: str = Field(default="", max_length=GREETING_MAX)
    starter_questions: list[ShortText] = Field(
        default_factory=list, max_length=STARTER_QUESTIONS_MAX
    )
    ui_text: UiText = Field(default_factory=UiText)
    # After how many replies Visitors are asked to rate the Conversation; 0 asks only at the end.
    rating_prompt_after: int = Field(default=3, ge=0, le=RATING_PROMPT_AFTER_MAX)


class FailMode(enum.StrEnum):
    """What happens when the LLM classifier's provider errors: open lets the message through,
    closed treats it as flagged."""

    OPEN = "open"
    CLOSED = "closed"


class Guardrails(BaseModel):
    """Stored and versioned with the Agent; enforced from spec 08. A message the input
    Guardrail flags is always refused: there is no setting for what it does."""

    model_config = _STRICT

    @model_validator(mode="before")
    @classmethod
    def _ignore_input_mode(cls, data: Any) -> Any:
        """Drops ``input_mode``, the old setting that could let a flagged message through (warn
        and log): Drafts and Versions saved with it still load, and it is ignored."""
        if isinstance(data, dict) and "input_mode" in data:
            return {key: value for key, value in data.items() if key != "input_mode"}
        return data

    # An optional LLM classifier: a chat model of a chat-capable credential.
    classifier: ModelChoice | None = None
    fail_mode: FailMode = FailMode.CLOSED
    refusal_text: str = Field(
        default=DEFAULT_REFUSAL_TEXT, min_length=1, max_length=REFUSAL_TEXT_MAX
    )


class AgentConfig(BaseModel):
    model_config = _STRICT

    behaviour: Behaviour = Field(default_factory=Behaviour)
    retrieval: Retrieval = Field(default_factory=Retrieval)
    experience: Experience = Field(default_factory=Experience)
    guardrails: Guardrails = Field(default_factory=Guardrails)
