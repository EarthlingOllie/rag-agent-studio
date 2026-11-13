"""The attack evaluation suite's case file: its schema, and loading it.

The case file (``backend/evals/attack_suite.json``) is data in the repo, versioned twice: its
``schema_version`` says which shape of file this module reads (the JSON Schema generated from
it is committed beside it as ``attack_suite.schema.json``), and its ``suite_version`` names
the set of cases, so reports from different runs can be compared.

Every case runs against one fictional Agent: the suite's system prompt and Knowledge Base. A
case has an ID, a category, the Visitor's turns (several for a multi-turn escalation), optional
poisoned Document content (retrieved first, like a relevant Document an attacker uploaded), the
input mode and Flagged Chunk mode it runs with, the markers whose appearance in a reply means
the attack worked, whether it is a benign control, and what each Guardrail layer is expected to
do (``Expected``).

Every case runs once in each Retrieval Mode (ADR-0015). It is expected to do the same in both,
unless it gives ``expected_agentic``: what each layer should do in Agentic mode instead, for an
attack only an Agent with Knowledge Search can attempt.
"""

import enum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.agents.config import RetrievalMode

SCHEMA_VERSION = 1

CASE_FILE = Path(__file__).resolve().parents[2] / "evals" / "attack_suite.json"
SCHEMA_FILE = CASE_FILE.with_name("attack_suite.schema.json")


class Category(enum.StrEnum):
    # Telling the Agent to drop its instructions and do something else.
    INSTRUCTION_OVERRIDE = "instruction_override"
    # Asking for the system prompt, the hidden instructions or the Canary token.
    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"
    # Giving the Agent a persona or a game that has no rules.
    ROLEPLAY_JAILBREAK = "roleplay_jailbreak"
    # Instructions hidden in a Document the Agent retrieves.
    INDIRECT_INJECTION = "indirect_injection"
    # An attack disguised: base64, lookalike letters, another language.
    ENCODING_BASE64 = "encoding_base64"
    ENCODING_HOMOGLYPH = "encoding_homoglyph"
    ENCODING_TRANSLATION = "encoding_translation"
    # An attack spread over several turns.
    MULTI_TURN_ESCALATION = "multi_turn_escalation"
    # A genuine question: the control that measures false positives.
    BENIGN = "benign"


class IngestionOutcome(enum.StrEnum):
    """What the ingestion scan did with the case's Document."""

    # Flagged, and quarantined: kept out of retrieval (no setting lets it in).
    EXCLUDED = "excluded"
    PASSED = "passed"


class InputOutcome(enum.StrEnum):
    """What the input Guardrail did, at its strongest over the case's turns."""

    BLOCKED = "blocked"
    PASSED = "passed"


class CanaryOutcome(enum.StrEnum):
    """What the Canary token caught, at its strongest over the case's turns."""

    # The canary started to stream: the reply was cut off and replaced.
    REPLACED = "replaced"
    # An encoded canary was found after the reply was sent.
    FLAGGED = "flagged"
    QUIET = "quiet"


class AnswerOutcome(enum.StrEnum):
    """Whether any reply the Visitor received carries one of the case's markers."""

    HARMLESS = "harmless"
    COMPROMISED = "compromised"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Expected(_Strict):
    """What each layer should do. ``ingestion`` is given exactly when the case has a Document."""

    ingestion: IngestionOutcome | None = None
    input: InputOutcome
    canary: CanaryOutcome
    answer: AnswerOutcome


NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class Case(_Strict):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    category: Category
    description: NonEmpty
    turns: Annotated[list[NonEmpty], Field(min_length=1)]
    # Poisoned Document content, retrieved ahead of the Knowledge Base.
    document: NonEmpty | None = None
    # Text that, appearing in any reply (ignoring case), shows the attack worked.
    markers: list[NonEmpty] = Field(default_factory=list)
    # A known weakness or false positive the expected outcome records: shown in the report.
    note: NonEmpty | None = None
    expected: Expected
    # What each layer should do in Agentic Retrieval Mode, when that differs from ``expected``.
    expected_agentic: Expected | None = None

    @property
    def benign(self) -> bool:
        return self.category is Category.BENIGN

    def expected_in(self, mode: RetrievalMode) -> Expected:
        """What each layer should do when the case runs in Retrieval Mode ``mode``."""
        if mode is RetrievalMode.AGENTIC and self.expected_agentic is not None:
            return self.expected_agentic
        return self.expected

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.benign and self.markers:
            raise ValueError(f"{self.id}: a benign case has no markers")
        if not self.benign and not self.markers:
            raise ValueError(f"{self.id}: an attack case needs a marker that shows it worked")
        for name, expected in (
            ("expected", self.expected),
            ("expected_agentic", self.expected_agentic),
        ):
            if expected is not None and (self.document is None) != (expected.ingestion is None):
                raise ValueError(
                    f"{self.id}: {name}.ingestion is given exactly when the case has a document"
                )
        return self


class KnowledgeChunk(_Strict):
    document: NonEmpty
    text: NonEmpty


class Suite(_Strict):
    schema_version: Literal[1]
    suite_version: NonEmpty
    # The fictional Agent's system prompt; extraction cases mark a secret written in it.
    system_prompt: NonEmpty
    knowledge_base: Annotated[list[KnowledgeChunk], Field(min_length=1)]
    cases: Annotated[list[Case], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"Duplicate case IDs: {', '.join(duplicates)}")
        return self

    def only(self, *ids: str) -> "Suite":
        """The suite with just the named cases, in the order named."""
        by_id = {case.id: case for case in self.cases}
        return self.model_copy(update={"cases": [by_id[i] for i in ids]})


def load_suite(path: Path = CASE_FILE) -> Suite:
    return Suite.model_validate_json(path.read_text(encoding="utf-8"))


def json_schema() -> dict[str, object]:
    """The case file's JSON Schema, as committed in ``SCHEMA_FILE``."""
    schema = Suite.model_json_schema()
    schema["$id"] = f"attack_suite.schema.v{SCHEMA_VERSION}.json"
    return schema
