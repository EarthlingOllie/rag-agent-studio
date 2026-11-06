"""Citations: which of the Chunks given to the model an answer cites.

The model cites a Chunk by its label (``C1``, ``C2`` …; see ``app.runtime.prompt``). Where the
model supports structured output it returns the labels it cites beside the answer
(``CitedAnswer``); otherwise the labels are parsed out of the answer text, written as ``[C1]``.
Either way each label is resolved back to its Chunk; a label that matches no Chunk given to the
model is dropped, and a Chunk cited twice counts once.
"""

import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from app.retrieval.service import Candidate
from app.runtime.prompt import chunk_label

_LABEL = re.compile(r"\[(C\d+)\]")


class CitedAnswer(BaseModel):
    """The structured output asked of models that support it. Both fields have defaults so a
    partly streamed answer validates and its text can be streamed as it arrives."""

    answer: str = Field(default="", description="The answer to the question.")
    citations: list[str] = Field(
        default_factory=list,
        description="The labels of the excerpts the answer uses, such as C1.",
    )


def labels_in(text: str) -> list[str]:
    """The ``[C1]``-style labels written in ``text``, in order."""
    return _LABEL.findall(text)


def resolve(labels: Iterable[str], chunks: Sequence[Candidate]) -> list[Candidate]:
    """The Chunks the labels name, in the order first cited."""
    by_label = {chunk_label(chunk.rank): chunk for chunk in chunks}
    cited: dict[str, Candidate] = {}
    for label in labels:
        # Structured citations may come as "[C1]" or "c1" as well as "C1".
        key = label.strip().strip("[]").upper()
        if key in by_label:
            cited.setdefault(key, by_label[key])
    return list(cited.values())
