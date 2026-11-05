"""AgentConfig: everything that shapes how an Agent answers, as one Pydantic model.

It is stored as ``jsonb`` on the Agent's Draft and validated on every read and write. It starts
with the system prompt and top-k; later tickets add the remaining Behaviour, Retrieval,
Experience and Guardrails settings as new fields with defaults, so stored Drafts stay valid.
"""

from pydantic import BaseModel, ConfigDict, Field

SYSTEM_PROMPT_MAX = 20_000
TOP_K_MAX = 20

# Unknown settings are refused. In responses every field is present, so the generated client
# types a saved AgentConfig as complete while requests may leave fields to their defaults.
_STRICT = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Behaviour(BaseModel):
    model_config = _STRICT

    system_prompt: str = Field(default="", max_length=SYSTEM_PROMPT_MAX)


class Retrieval(BaseModel):
    model_config = _STRICT

    # How many Chunks are given to the model with each question.
    top_k: int = Field(default=5, ge=1, le=TOP_K_MAX)


class AgentConfig(BaseModel):
    model_config = _STRICT

    behaviour: Behaviour = Field(default_factory=Behaviour)
    retrieval: Retrieval = Field(default_factory=Retrieval)
