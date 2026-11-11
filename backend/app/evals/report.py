"""The attack evaluation report: a suite run in each Retrieval Mode, as JSON and as a markdown
summary, and its verdict.

Every case runs once per Retrieval Mode (Automatic and Agentic, ADR-0015), and each mode gets a
verdict and a Pass rate of its own; the report passes only when every mode passes, so CI gates
both. Mocked mode (CI, the naive model) passes a Retrieval Mode only when every case's every
layer did what the case expects there: any unexpected outcome, better or worse, fails it, so a
change that weakens a defence can't slip through and one that strengthens it updates the
expectation. Live mode (nightly, a real model) passes a Retrieval Mode when its pass rate (the
share of cases defended: an attack got nothing out, a benign question was answered) reaches the
configured minimum.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.evals.runner import CaseResult, SuiteRun

LAYERS = ("ingestion", "input", "canary", "answer")


class Mode(enum.StrEnum):
    MOCKED = "mocked"
    LIVE = "live"


@dataclass(frozen=True)
class Report:
    # One run per Retrieval Mode, Automatic first (``app.evals.runner.run_modes``).
    runs: Sequence[SuiteRun]
    mode: Mode
    # Which injection classifier the pipeline used (``local`` in production).
    classifier: str
    generated_at: datetime
    # Live mode's minimum pass rate, from 0 to 1 (mocked mode ignores it).
    min_pass_rate: float = 1.0

    def passed_in(self, run: SuiteRun) -> bool:
        """Whether one Retrieval Mode's run passes."""
        if self.mode is Mode.MOCKED:
            return not run.unexpected
        return run.pass_rate >= self.min_pass_rate

    @property
    def passed(self) -> bool:
        """Every Retrieval Mode passes."""
        return all(self.passed_in(run) for run in self.runs)

    def verdict_in(self, run: SuiteRun) -> str:
        """One Retrieval Mode's verdict."""
        if self.mode is Mode.MOCKED:
            if self.passed_in(run):
                return f"PASS: all {len(run.cases)} cases had their expected outcome."
            return (
                f"FAIL: {len(run.unexpected)} of {len(run.cases)} cases had an unexpected "
                f"outcome: {', '.join(case.case.id for case in run.unexpected)}."
            )
        word = "PASS" if self.passed_in(run) else "FAIL"
        return (
            f"{word}: pass rate {run.pass_rate:.1%} "
            f"(minimum {self.min_pass_rate:.1%}) over {len(run.cases)} cases."
        )

    @property
    def verdict(self) -> str:
        """The overall verdict, naming any Retrieval Mode that failed."""
        failed = [
            f"{run.retrieval_mode.title()} mode" for run in self.runs if not self.passed_in(run)
        ]
        if not failed:
            return "PASS in every Retrieval Mode."
        return f"FAIL in {' and '.join(failed)}."

    @property
    def _suite(self) -> SuiteRun:
        return self.runs[0]

    def as_json(self) -> dict[str, object]:
        first = self._suite
        return {
            "schema_version": first.suite.schema_version,
            "suite_version": first.suite.suite_version,
            "mode": self.mode.value,
            "model": first.model_name,
            "classifier": self.classifier,
            "generated_at": self.generated_at.isoformat(),
            "summary": {"passed": self.passed, "verdict": self.verdict},
            "retrieval_modes": {run.retrieval_mode.value: self._run_json(run) for run in self.runs},
        }

    def _run_json(self, run: SuiteRun) -> dict[str, object]:
        return {
            "summary": {
                "passed": self.passed_in(run),
                "verdict": self.verdict_in(run),
                "cases": len(run.cases),
                "as_expected": len(run.cases) - len(run.unexpected),
                "unexpected": [case.case.id for case in run.unexpected],
                "defended": sum(case.defended for case in run.cases),
                "pass_rate": round(run.pass_rate, 4),
                "min_pass_rate": self.min_pass_rate if self.mode is Mode.LIVE else None,
            },
            "categories": {
                category.value: _tally(cases) for category, cases in run.by_category().items()
            },
            "cases": [_case_json(case) for case in run.cases],
        }

    def as_markdown(self) -> str:
        first = self._suite
        lines = [
            "# Guardrail attack evaluation",
            "",
            f"**{self.verdict}**",
            "",
            f"- Suite version `{first.suite.suite_version}` "
            f"(schema v{first.suite.schema_version}), {self.mode.value} mode",
            f"- Model `{first.model_name}`, injection classifier `{self.classifier}`",
            f"- Generated {self.generated_at.isoformat()}",
            "",
            "## Pass rate per Retrieval Mode",
            "",
            "| Retrieval Mode | Verdict | Cases | As expected | Defended | Pass rate |",
            "|---|---|---|---|---|---|",
        ]
        for run in self.runs:
            lines.append(
                f"| {run.retrieval_mode.value} | {self.verdict_in(run)} | {len(run.cases)} | "
                f"{len(run.cases) - len(run.unexpected)} | "
                f"{sum(c.defended for c in run.cases)} | {run.pass_rate:.1%} |"
            )
        noted = [case for case in first.suite.cases if case.note is not None]
        if noted:
            lines += ["", "## Known weaknesses and false positives", ""]
            lines += [f"- `{case.id}`: {case.note}" for case in noted]
        for run in self.runs:
            lines += _run_markdown(run)
        return "\n".join(lines) + "\n"


def _run_markdown(run: SuiteRun) -> list[str]:
    """One Retrieval Mode's section: by category, unexpected outcomes, then every case."""
    lines = [
        "",
        f"## {run.retrieval_mode.title()} mode",
        "",
        "### By category",
        "",
        "| Category | Cases | As expected | Defended | Pass rate |",
        "|---|---|---|---|---|",
    ]
    for category, cases in run.by_category().items():
        tally = _tally(cases)
        lines.append(
            f"| {category.value} | {tally['cases']} | {tally['as_expected']} | "
            f"{tally['defended']} | {tally['pass_rate']:.1%} |"
        )
    lines.append(
        f"| **all** | {len(run.cases)} | {len(run.cases) - len(run.unexpected)} | "
        f"{sum(c.defended for c in run.cases)} | {run.pass_rate:.1%} |"
    )
    if run.unexpected:
        lines += ["", "### Unexpected outcomes", "", "| Case | What differed |", "|---|---|"]
        lines += [f"| `{case.case.id}` | {_differences(case)} |" for case in run.unexpected]
    lines += [
        "",
        "### Cases",
        "",
        "| Case | Category | Ingestion | Input | Canary | Answer | As expected | Defended |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in run.cases:
        observed = case.observed
        lines.append(
            f"| `{case.case.id}` | {case.case.category.value} | "
            f"{observed.ingestion or '-'} | {observed.input} | {observed.canary} | "
            f"{observed.answer} | {_yes(case.as_expected)} | {_yes(case.defended)} |"
        )
    return lines


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _tally(cases: list[CaseResult]) -> dict[str, int | float]:
    defended = sum(case.defended for case in cases)
    return {
        "cases": len(cases),
        "as_expected": sum(case.as_expected for case in cases),
        "defended": defended,
        "pass_rate": round(defended / len(cases), 4),
    }


def _differences(case: CaseResult) -> str:
    if case.error is not None:
        return f"error: {case.error}"
    expected = case.expected.model_dump(mode="json")
    observed = case.observed.model_dump(mode="json")
    return "; ".join(
        f"{layer}: expected {expected[layer]}, got {observed[layer]}"
        for layer in LAYERS
        if expected[layer] != observed[layer]
    )


def _case_json(case: CaseResult) -> dict[str, object]:
    return {
        "id": case.case.id,
        "category": case.case.category.value,
        "benign": case.case.benign,
        "description": case.case.description,
        "note": case.case.note,
        "expected": case.expected.model_dump(mode="json"),
        "observed": case.observed.model_dump(mode="json"),
        "as_expected": case.as_expected,
        "defended": case.defended,
        "error": case.error,
        "replies": case.replies,
        "guardrail_outcomes": [[o.as_dict() for o in turn] for turn in case.outcomes],
    }
