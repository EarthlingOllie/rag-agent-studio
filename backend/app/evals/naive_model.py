"""The naive model: a mocked chat model that does what injected instructions tell it.

The evaluation suite runs against it in CI so that the Guardrails are what is tested, not a real
model's own refusals (if the mock refused attacks, the suite would only test the mock). It is a
Pydantic AI ``FunctionModel`` answering in plain text, and it reads every user prompt it is
given (the remembered turns and the question with its data blocks: retrieved Chunks included)
the way a gullible model would:

- it reads lookalike letters as the letters they look like, and decodes base64 it finds;
- asked to reveal its instructions (in English, French, German or Spanish), it recites its
  whole system text, platform preamble and Canary token first;
- asked for its secret token in base64, it gives the Canary token base64-encoded;
- asked to say a codeword (anything shaped like ``PWNED-1001``, in any language), it says it;
- otherwise it answers from the first retrieved Chunk, citing it.

Its replies stream in short pieces, so a recited Canary token straddles stream chunks.
"""

import base64
import binascii
import re
import unicodedata
from collections.abc import AsyncIterator

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.runtime.prompt import CHUNKS_CLOSE, CHUNKS_OPEN

MODEL_NAME = "naive-mock"
# How many characters each streamed piece holds.
PIECE = 7

# Cyrillic and Greek letters that look like Latin ones (NFKC folds fullwidth and others).
_LOOKALIKES = str.maketrans(
    "аеорсхуіјѕԁһАВЕКМНОРСТХІЈЅԌαοερτυνκΑΒΕΗΙΚΜΝΟΡΤΧΥΖ",
    "aeopcxyijsdhABEKMHOPCTXIJSGaoeptuvkABEHIKMNOPTXYZ",
)
_BASE64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
CODEWORD = re.compile(r"\b[A-Z][A-Z0-9]+-\d{3,}\b")
_REVEAL_VERBS = re.compile(
    r"\b(?:print|repeat|show|output|reveal|quote|recite|recites|read|write out|tell me|"
    r"gib|zeig|zeige|affiche|montre|muestra|imprime|dime)\b",
    re.IGNORECASE,
)
_REVEAL_OBJECTS = re.compile(
    r"system ?prompt|systemprompt|prompt syst[eè]me|everything above|told before|"
    r"(?:hidden|initial|secret|actual|original|your) instructions|"
    r"(?:deine|ihre) anweisungen|tus instrucciones|vos instructions",
    re.IGNORECASE,
)
_TOKEN_IN_BASE64 = re.compile(r"(?:secret|canary) token.{0,40}base ?64", re.IGNORECASE)
_CANARY = re.compile(r"Secret canary token: (\w+)\.")
_FIRST_EXCERPT = re.compile(
    re.escape(CHUNKS_OPEN)
    + r"\n\[(C\d+)\] ([^\n]+)\n(.+?)(?:\n\n\[C\d+\] |\n"
    + re.escape(CHUNKS_CLOSE)
    + ")",
    re.DOTALL,
)


def _parts(messages: list[ModelMessage], kind: type[SystemPromptPart | UserPromptPart]) -> str:
    return "\n".join(
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, kind) and isinstance(part.content, str)
    )


def _decoded(text: str) -> list[str]:
    """The printable text of every base64 run in ``text``."""
    found = []
    for run in _BASE64.findall(text):
        try:
            decoded = base64.b64decode(run, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            continue
        if decoded.isprintable():
            found.append(decoded)
    return found


def understand(text: str) -> str:
    """What the naive model reads in ``text``: lookalikes folded, base64 decoded and added."""
    folded = unicodedata.normalize("NFKC", text).translate(_LOOKALIKES)
    return "\n".join([folded, *_decoded(folded)])


def naive_answer(messages: list[ModelMessage]) -> str:
    system = _parts(messages, SystemPromptPart)
    read = understand(_parts(messages, UserPromptPart))
    if _REVEAL_VERBS.search(read) and _REVEAL_OBJECTS.search(read):
        return f"Of course. My instructions are:\n{system}"
    canary = _CANARY.search(system)
    if canary is not None and _TOKEN_IN_BASE64.search(read):
        return f"Here it is: {base64.b64encode(canary.group(1).encode()).decode()}"
    codeword = CODEWORD.search(read)
    if codeword is not None:
        return f"Sure! {codeword.group(0)}"
    excerpt = _FIRST_EXCERPT.search(read)
    if excerpt is None:
        return "I don't know."
    label, document, chunk = excerpt.groups()
    return f"From {document} [{label}]: {' '.join(chunk.split())}"


async def _stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    answer = naive_answer(messages)
    for start in range(0, len(answer), PIECE):
        yield answer[start : start + PIECE]


def naive_model() -> Model:
    # The runtime always streams, so the model has only a streaming function.
    return FunctionModel(
        stream_function=_stream,
        model_name=MODEL_NAME,
        profile={"supports_json_schema_output": False},
    )
