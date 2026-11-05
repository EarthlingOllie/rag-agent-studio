"""AgentConfig: everything that shapes how an Agent answers, as one Pydantic model.

It is stored as ``jsonb`` on the Agent's Draft and validated on every read and write. It starts
with the system prompt and top-k; later tickets add the remaining Behaviour, Retrieval,
Experience and Guardrails settings as new fields with defaults, so stored Drafts stay valid.
"""

from pydantic import BaseModel, ConfigDict, Field

SYSTEM_PROMPT_MAX = 20_000
FALLBACK_TEXT_MAX = 2_000
TOP_K_MAX = 20
DEFAULT_FALLBACK_TEXT = "Sorry, I don't know the answer to that."

# Unknown settings are refused. In responses every field is present, so the generated client
# types a saved AgentConfig as complete while requests may leave fields to their defaults.
_STRICT = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Behaviour(BaseModel):
    model_config = _STRICT

    system_prompt: str = Field(default="", max_length=SYSTEM_PROMPT_MAX)
    # The reply when retrieval finds no Chunk at or above the minimum score; the model isn't asked.
    fallback_text: str = Field(
        default=DEFAULT_FALLBACK_TEXT, min_length=1, max_length=FALLBACK_TEXT_MAX
    )


class Retrieval(BaseModel):
    model_config = _STRICT

    # How many Chunks are given to the model with each question.
    top_k: int = Field(default=5, ge=1, le=TOP_K_MAX)
    # The hybrid weighting: semantic search's share of the fused score, keyword search having
    # the rest. 1 is semantic search alone, 0 keyword search alone.
    hybrid_weight: float = Field(default=0.5, ge=0, le=1)
    # The minimum score: the relevance (0 to 1) a Chunk needs to be given to the model.
    min_score: float = Field(default=0, ge=0, le=1)


class AgentConfig(BaseModel):
    model_config = _STRICT

    behaviour: Behaviour = Field(default_factory=Behaviour)
    retrieval: Retrieval = Field(default_factory=Retrieval)
