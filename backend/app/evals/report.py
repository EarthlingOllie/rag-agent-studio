"""The attack evaluation report: a suite run as JSON and as a markdown summary, and its verdict.

Mocked mode (CI, the naive model) passes only when every case's every layer did what the case
expects: any unexpected outcome, better or worse, fails it, so a change that weakens a defence
can't slip through and one that strengthens it updates the expectation. Live mode (nightly, a
real model) passes when the pass rate (the share of cases defended: an attack got nothing out,
a benign question was answered) reaches the configured minimum.
"""

import enum
from dataclasses import dataclass
from datetime import datetime

from app.evals.runner import CaseResult, SuiteRun

LAYERS = ("ingestion", "input", "canary", "answer")


class Mode(enum.StrEnum):
    MOCKED = "mocked"
    LIVE = "live"


@dataclass(frozen=True)
class Report:
    run: SuiteRun
    mode: Mode
    # Which injection classifier the pipeline used (``local`` in production).
    classifier: str
    generated_at: datetime
    # Live mode's minimum pass rate, from 0 to 1 (mocked mode ignores it).
    min_pass_rate: float = 1.0

    @property
    def passed(self) -> bool:
        if self.mode is Mode.MOCKED:
            return not self.run.unexpected
        return self.run.pass_rate >= self.min_pass_rate

    @property
    def verdict(self) -> str:
        run = self.run
        if self.mode is Mode.MOCKED:
            if self.passed:
                return f"PASS: all {len(run.cases)} cases had their expected outcome."
            return (
                f"FAIL: {len(run.unexpected)} of {len(run.cases)} cases had an unexpected "
                f"outcome: {', '.join(case.case.id for case in run.unexpected)}."
            )
        word = "PASS" if self.passed else "FAIL"
        return (
            f"{word}: pass rate {run.pass_rate:.1%} "
            f"(minimum {self.min_pass_rate:.1%}) over {len(run.cases)} cases."
        )

    def as_json(self) -> dict[str, object]:
        run = self.run
        return {
            "schema_version": run.suite.schema_version,
            "suite_version": run.suite.suite_version,
            "mode": self.mode.value,
            "model": run.model_name,
            "classifier": self.classifier,
            "generated_at": self.generated_at.isoformat(),
            "summary": {
                "passed": self.passed,
                "verdict": self.verdict,
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
        run = self.run
        lines = [
            "# Guardrail attack evaluation",
            "",
            f"**{self.verdict}**",
            "",
            f"- Suite version `{run.suite.suite_version}` (schema v{run.suite.schema_version}), "
            f"{self.mode.value} mode",
            f"- Model `{run.model_name}`, injection classifier `{self.classifier}`",
            f"- Generated {self.generated_at.isoformat()}",
            "",
            "## By category",
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
            lines += ["", "## Unexpected outcomes", "", "| Case | What differed |", "|---|---|"]
            lines += [f"| `{case.case.id}` | {_differences(case)} |" for case in run.unexpected]
        noted = [case for case in run.cases if case.case.note is not None]
        if noted:
            lines += ["", "## Known weaknesses and false positives", ""]
            lines += [f"- `{case.case.id}`: {case.case.note}" for case in noted]
        lines += [
            "",
            "## Cases",
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
        return "\n".join(lines) + "\n"


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
    expected = case.case.expected.model_dump(mode="json")
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
        "expected": case.case.expected.model_dump(mode="json"),
        "observed": case.observed.model_dump(mode="json"),
        "as_expected": case.as_expected,
        "defended": case.defended,
        "error": case.error,
        "replies": case.replies,
        "guardrail_outcomes": [[o.as_dict() for o in turn] for turn in case.outcomes],
    }
