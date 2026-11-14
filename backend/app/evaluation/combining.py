"""Combining a case's repeats into its result on a side, and a side's cases into its Evaluation
score.

A repeat passes when none of its Verdicts fails (a Stale one is neither pass nor fail). A case
passes on a side when most of its answered repeats pass; a tie is no majority. A case is
Unsteady when its answered repeats disagree, and an Error on a side when every repeat there
errored. Error cases are left out of the side's Evaluation score.
"""

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationVerdict,
    ResultStatus,
    VerdictOutcome,
)


class CaseOutcome(enum.StrEnum):
    PASS = "pass"  # noqa: S105 (a case's outcome, not a password)
    FAIL = "fail"
    ERROR = "error"


@dataclass(frozen=True)
class Repeat:
    result: EvaluationCaseResult
    verdicts: Sequence[EvaluationVerdict]

    @property
    def answered(self) -> bool:
        return self.result.status == ResultStatus.ANSWERED

    @property
    def passed(self) -> bool:
        """Whether the repeat answered and none of its Verdicts failed."""
        return self.answered and all(v.outcome != VerdictOutcome.FAIL for v in self.verdicts)


@dataclass(frozen=True)
class SideResult:
    """A case's result on one side of a Run, from its repeats so far."""

    outcome: CaseOutcome
    passed: int
    answered: int
    repeats: int
    unsteady: bool


def side_result(repeats: Sequence[Repeat]) -> SideResult:
    answered = [repeat for repeat in repeats if repeat.answered]
    passed = sum(repeat.passed for repeat in answered)
    if not answered:
        outcome = CaseOutcome.ERROR
    else:
        outcome = CaseOutcome.PASS if passed * 2 > len(answered) else CaseOutcome.FAIL
    return SideResult(
        outcome=outcome,
        passed=passed,
        answered=len(answered),
        repeats=len(repeats),
        unsteady=0 < passed < len(answered),
    )


@dataclass(frozen=True)
class Score:
    passed: int
    failed: int
    errored: int

    @property
    def score(self) -> float | None:
        """The share of the cases that weren't Errors that passed; None with no such case."""
        scored = self.passed + self.failed
        return None if scored == 0 else self.passed / scored


def score(results: Iterable[SideResult]) -> Score:
    outcomes = [result.outcome for result in results]
    return Score(
        passed=outcomes.count(CaseOutcome.PASS),
        failed=outcomes.count(CaseOutcome.FAIL),
        errored=outcomes.count(CaseOutcome.ERROR),
    )
