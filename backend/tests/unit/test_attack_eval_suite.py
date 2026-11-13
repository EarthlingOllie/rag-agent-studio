"""The attack evaluation suite's case file: the committed suite is valid against its versioned
schema and covers every attack category and benign controls; malformed cases are refused."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evals import schema
from app.evals.suite import CASE_FILE, SCHEMA_FILE, Case, Category, Suite, json_schema, load_suite

TINY = Path(__file__).parent.parent / "fixtures" / "evals" / "tiny_suite.json"


def test_the_committed_schema_matches_the_case_file_model() -> None:
    # Regenerate with: uv run python -m app.evals.schema
    assert json.loads(SCHEMA_FILE.read_text()) == json_schema()


def test_the_committed_suite_covers_every_category_with_benign_controls() -> None:
    suite = load_suite(CASE_FILE)

    assert suite.schema_version == 1
    categories = {case.category for case in suite.cases}
    assert categories == set(Category)
    benign = [case for case in suite.cases if case.benign]
    assert len(benign) >= 8
    assert any(len(case.turns) > 1 for case in suite.cases if not case.benign)
    assert any(case.document is not None for case in suite.cases)
    # A flagged Document is quarantined in both Retrieval Modes, so the one attack only an Agent
    # with Knowledge Search could make (``indirect-search-for-canary``) now expects the same in
    # both; the tiny suite keeps a case whose Document the scan passes for ``expected_agentic``.
    assert by_id(suite, "indirect-search-for-canary").expected.ingestion == "excluded"


def by_id(suite: Suite, case_id: str) -> Case:
    (case,) = [case for case in suite.cases if case.id == case_id]
    return case


def tiny_with(tmp_path: Path, **changes: object) -> Path:
    suite = json.loads(TINY.read_text())
    suite["cases"][0].update(changes)
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite))
    return path


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"category": "benign"}, "a benign case has no markers"),
        ({"markers": []}, "an attack case needs a marker that shows it worked"),
        ({"document": "Hidden text."}, "expected.ingestion is given exactly when"),
        (
            {
                "expected_agentic": {
                    "ingestion": "passed",
                    "input": "blocked",
                    "canary": "quiet",
                    "answer": "harmless",
                }
            },
            "expected_agentic.ingestion is given exactly when",
        ),
        ({"id": "extraction-canary"}, "Duplicate case IDs: extraction-canary"),
        ({"id": "Not An ID"}, "String should match pattern"),
        ({"turns": []}, "at least 1 item"),
        ({"surprise": True}, "Extra inputs are not permitted"),
    ],
)
def test_a_malformed_case_is_refused(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        load_suite(tiny_with(tmp_path, **changes))


def test_an_unknown_schema_version_is_refused(tmp_path: Path) -> None:
    suite = json.loads(TINY.read_text())
    suite["schema_version"] = 2
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite))

    with pytest.raises(ValidationError, match="schema_version"):
        load_suite(path)


def test_the_schema_command_writes_the_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "attack_suite.schema.json"
    monkeypatch.setattr(schema, "SCHEMA_FILE", target)

    schema.write_schema()

    assert json.loads(target.read_text()) == json_schema()
