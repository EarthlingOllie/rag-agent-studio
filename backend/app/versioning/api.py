"""Response shapes shared by the diff routes of Agents and Project Instructions."""

from typing import Literal

from pydantic import BaseModel

from app.versioning.diff import Line


class DiffLineOut(BaseModel):
    # equal (on both sides), delete (only before) or insert (only after).
    op: Literal["equal", "delete", "insert"]
    text: str


def lines_out(lines: list[Line]) -> list[DiffLineOut]:
    return [DiffLineOut(op=line.op, text=line.text) for line in lines]
