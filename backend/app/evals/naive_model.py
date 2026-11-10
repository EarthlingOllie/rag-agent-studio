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

Given Knowledge Search (Agentic Retrieval Mode, ADR-0015), it first searches with the Visitor's
question, then reads what the Search returned as it reads retrieved Chunks. A Chunk telling it
to search for its secret token makes it search again with its Canary token (an injection that
would leak the canary into the query, the Trace and the logs), and it then says it did.

Its replies stream in short pieces, so a recited Canary token straddles stream chunks.
"""

import base64
import binascii
import json
import re
import unicodedata
from collections.abc import AsyncIterator

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

from app.runtime.prompt import CHUNKS_CLOSE, CHUNKS_OPEN, INPUT_CLOSE, INPUT_OPEN, KNOWLEDGE_SEARCH

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
_SEARCH_FOR_TOKEN = re.compile(
    r"search(?:es|ing)? (?:the knowledge base )?for (?:your|its|the) (?:secret|canary) token",
    re.IGNORECASE,
)
SEARCHED_FOR_TOKEN = "Done: I searched the knowledge base for my secret token."
_VISITOR_BLOCK = re.compile(f"{re.escape(INPUT_OPEN)}\n(.*?)\n{re.escape(INPUT_CLOSE)}", re.DOTALL)
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


def _search_results(messages: list[ModelMessage]) -> list[str]:
    """What each Knowledge Search returned, in order."""
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


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


def naive_search(messages: list[ModelMessage], tools: list[str]) -> str | None:
    """The query the naive model searches with next, if it searches: offered Knowledge Search,
    it first searches with the Visitor's question; then, if a Search returned a request to
    search for its secret token, once more with its Canary token."""
    if KNOWLEDGE_SEARCH not in tools:
        return None
    results = _search_results(messages)
    if not results:
        # The Visitor input block's text: the question being answered.
        return _VISITOR_BLOCK.findall(_parts(messages, UserPromptPart))[-1]
    canary = _CANARY.search(_parts(messages, SystemPromptPart))
    if (
        len(results) == 1
        and canary is not None
        and _SEARCH_FOR_TOKEN.search(understand(results[0]))
    ):
        return f"secret token {canary.group(1)}"
    return None


def naive_answer(messages: list[ModelMessage]) -> str:
    system = _parts(messages, SystemPromptPart)
    results = _search_results(messages)
    read = understand("\n".join([_parts(messages, UserPromptPart), *results]))
    if _REVEAL_VERBS.search(read) and _REVEAL_OBJECTS.search(read):
        return f"Of course. My instructions are:\n{system}"
    canary = _CANARY.search(system)
    if canary is not None and _TOKEN_IN_BASE64.search(read):
        return f"Here it is: {base64.b64encode(canary.group(1).encode()).decode()}"
    if len(results) > 1 and _SEARCH_FOR_TOKEN.search(read):
        return SEARCHED_FOR_TOKEN
    codeword = CODEWORD.search(read)
    if codeword is not None:
        return f"Sure! {codeword.group(0)}"
    excerpt = _FIRST_EXCERPT.search(read)
    if excerpt is None:
        return "I don't know."
    label, document, chunk = excerpt.groups()
    return f"From {document} [{label}]: {' '.join(chunk.split())}"


async def _stream(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    query = naive_search(messages, [tool.name for tool in info.function_tools])
    if query is not None:
        args = json.dumps({"query": query})
        yield {0: DeltaToolCall(name=KNOWLEDGE_SEARCH, json_args=args, tool_call_id="search")}
        return
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
