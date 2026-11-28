"""What a Visitor hears of a reply in a Call (spec 20): the runtime's events turned into the text
the voice layer speaks.

- **Spoken text.** The reply's text is spoken without its Markdown (headings, emphasis, list
  markers, code marks, tables, links but their words) or its citation labels (``[C1]``); the
  saved Message and the Conversation log keep the full text with its sources. Text is spoken a
  sentence or line at a time, so markup split across streamed tokens is stripped whole.
- **The Searching status.** The first Search of a reply speaks the Searching status (or the
  Agent's UI text override of it) as a buffer phrase; later Searches of the reply say nothing.
- **Nothing spoken is taken back.** In Agentic Retrieval Mode a model response's text, and the
  Fallback Text sent as a response starts, may still be retracted until the reply's answer is
  known, so it is held back and spoken only once it can't be: when the answer's citations or
  its end arrive. A retracted response's held text is dropped unspoken. (Automatic replies are
  never retracted, so they are spoken as they stream.)
- **Outcomes.** A Canary trip stops the reply and speaks the replacement text; a Guardrail
  block speaks the refusal text. An unavailable outcome speaks the Unavailable text, and
  ``ended`` tells the turn endpoint to end the Call.
"""

import re

from app.embed.visitor_turn import Unavailable, VisitorTurnEvent
from app.guardrails.pipeline import RefusalEvent
from app.runtime.errors import ErrorEvent
from app.runtime.runtime import CitationEvent, ReplaceEvent, RetractEvent, SearchEvent, TokenEvent

# The widget's built-in Searching status, spoken unless the Agent rewords it.
SEARCHING_STATUS = "Searching the knowledge base…"

_FENCE = re.compile(r"^\s*(```|~~~)")
_RULE = re.compile(r"^\s*([-*_]\s*){3,}$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*$")
_LINE_MARKERS = re.compile(r"^\s*(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)+")
_CITATION = re.compile(r"\s*\[C\d+\]")
_IMAGE_OR_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_STRONG = re.compile(r"(\*\*|__)(.+?)\1")
_UNDERSCORED = re.compile(r"(?<!\w)_(\S(?:.*?\S)?)_(?!\w)")
_MARKS = re.compile(r"\*+|`+|~~|_{2,}")
_CELL_BORDERS = re.compile(r"^\s*\|\s*|\s*\|\s*$")
_CELL = re.compile(r"\s*\|\s*")
_SPACES = re.compile(r"[ \t]{2,}")
# Where a stretch of text can be spoken: after a line, or after a sentence and its space.
_BOUNDARY = re.compile(r"\n|[.!?:;](?=\s)\s*")


def _line(line: str) -> str | None:
    """A line's words without its block markup, or None for a line that is only markup."""
    if _FENCE.match(line) or _RULE.match(line) or _TABLE_DIVIDER.match(line):
        return None
    line = _LINE_MARKERS.sub("", line)
    if "|" in line:
        line = _CELL.sub(", ", _CELL_BORDERS.sub("", line))
    return line


def spoken_text(text: str, *, line_start: bool = True) -> str:
    """``text`` as it is spoken: without Markdown or citation labels. ``line_start`` says
    whether it starts a line, so its first line's block markup is markup."""
    lines = text.split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        bare = _line(line) if index or line_start else line
        if bare is not None:
            kept.append(bare)
    words = "\n".join(kept)
    words = _CITATION.sub("", words)
    words = _IMAGE_OR_LINK.sub(r"\1", words)
    words = _STRONG.sub(r"\2", words)
    words = _UNDERSCORED.sub(r"\1", words)
    words = _MARKS.sub("", words)
    return _SPACES.sub(" ", words)


class _Speaker:
    """Speaks streamed text a sentence or line at a time, stripped."""

    def __init__(self) -> None:
        self._pending = ""
        self._line_start = True

    def feed(self, text: str) -> str:
        self._pending += text
        end = 0
        for found in _BOUNDARY.finditer(self._pending):
            stretch = self._pending[: found.end()]
            # A link or code span still open at the boundary is spoken once it closes.
            if stretch.count("[") == stretch.count("]") and stretch.count("`") % 2 == 0:
                end = found.end()
        return self._take(end)

    def finish(self) -> str:
        return self._take(len(self._pending))

    def drop(self) -> None:
        self._pending = ""

    def _take(self, end: int) -> str:
        stretch, self._pending = self._pending[:end], self._pending[end:]
        if not stretch:
            return ""
        said = spoken_text(stretch, line_start=self._line_start)
        self._line_start = stretch.endswith("\n")
        return said


class Speech:
    """Turns one reply's events into what is spoken. ``retractable`` is true for an Agentic
    reply, whose text may be retracted until its answer is known."""

    def __init__(self, *, retractable: bool, searching_status: str, unavailable: str) -> None:
        self._retractable = retractable
        self._searching_status = searching_status
        self._unavailable = unavailable
        self._speaker = _Speaker()
        self._held = ""
        self._searched = False
        self._stopped = False
        # True once the reply was unavailable: the Call is to end.
        self.ended = False

    def hear(self, event: VisitorTurnEvent) -> list[str]:
        """What to speak for ``event``, in order (possibly nothing)."""
        if self._stopped:
            return []
        if isinstance(event, TokenEvent):
            if self._retractable:
                self._held += event.text
                return []
            return [self._speaker.feed(event.text)]
        if isinstance(event, RetractEvent):
            self._held = ""
            return []
        if isinstance(event, SearchEvent):
            if self._searched:
                return []
            self._searched = True
            return [f"{self._searching_status} "]
        if isinstance(event, ReplaceEvent | RefusalEvent):
            return self._stop(spoken_text(event.text))
        if isinstance(event, Unavailable | ErrorEvent):
            return [self.unavailable()]
        # A citation, or the saved answer: the reply's text is final, so all of it is spoken.
        held, self._held = self._held, ""
        said = self._speaker.feed(held)
        return [said, self._speaker.finish()] if not isinstance(event, CitationEvent) else [said]

    def unavailable(self) -> str:
        """The Agent can't answer: the Unavailable text is spoken, and the Call is to end."""
        self.ended = True
        return self._stop(self._unavailable)[0]

    def _stop(self, text: str) -> list[str]:
        """Drops what wasn't spoken yet and speaks ``text`` instead; nothing after it is."""
        self._stopped = True
        self._held = ""
        self._speaker.drop()
        return [text]
