"""Diffs of versioned configuration: what changed between two AgentConfigs, and between two
markdown texts.

- **Structural diff** (``diff_configs``). Every field of the two configurations is compared by
  its dotted path (``behaviour.temperature``, ``experience.ui_text.send_button``), in the
  AgentConfig's own field order. Groups are compared field by field; a value that is a group on
  one side and empty on the other (a Model choice set or cleared) is one change of the whole
  value. A list (Tags, starter questions) that differs is one change listing the items added
  and removed; a reordered list changes with nothing added or removed.
- **Text diff** (``diff_text``). A line diff, each line ``equal``, ``delete`` (only before) or
  ``insert`` (only after). Markdown fields (the system prompt) get one beside their change, and
  Project Instructions are compared with it.
"""

import difflib
from dataclasses import dataclass, field
from typing import Literal

from pydantic import JsonValue

from app.agents.config import AgentConfig

# The fields written in markdown, which also get a line diff.
MARKDOWN_FIELDS = frozenset({"behaviour.system_prompt"})


@dataclass(frozen=True)
class Line:
    op: Literal["equal", "delete", "insert"]
    text: str


@dataclass(frozen=True)
class FieldChange:
    path: str
    before: JsonValue
    after: JsonValue
    # For lists: the items only after, and only before.
    added: list[JsonValue] | None = None
    removed: list[JsonValue] | None = None
    # For markdown fields: the line diff.
    lines: list[Line] | None = field(default=None)


def diff_text(before: str, after: str) -> list[Line]:
    """The line diff turning ``before`` into ``after``."""
    old, new = before.splitlines(), after.splitlines()
    lines: list[Line] = []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            lines += [Line("equal", text) for text in old[i1:i2]]
            continue
        lines += [Line("delete", text) for text in old[i1:i2]]
        lines += [Line("insert", text) for text in new[j1:j2]]
    return lines


def _change(path: str, before: JsonValue, after: JsonValue) -> FieldChange:
    if isinstance(before, list) and isinstance(after, list):
        return FieldChange(
            path,
            before,
            after,
            added=[item for item in after if item not in before],
            removed=[item for item in before if item not in after],
        )
    if path in MARKDOWN_FIELDS:
        return FieldChange(path, before, after, lines=diff_text(str(before), str(after)))
    return FieldChange(path, before, after)


def _walk(
    prefix: str, before: dict[str, JsonValue], after: dict[str, JsonValue]
) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for key, old in before.items():
        new = after[key]
        path = f"{prefix}{key}"
        if old == new:
            continue
        if isinstance(old, dict) and isinstance(new, dict):
            changes += _walk(f"{path}.", old, new)
        else:
            changes.append(_change(path, old, new))
    return changes


def diff_configs(before: AgentConfig, after: AgentConfig) -> list[FieldChange]:
    """Every field that differs between two AgentConfigs, in the AgentConfig's field order."""
    return _walk("", before.model_dump(mode="json"), after.model_dump(mode="json"))
