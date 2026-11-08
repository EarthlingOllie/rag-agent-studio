"""``python -m app.evals.schema``: writes the case file's JSON Schema beside it."""

import json

from app.evals.suite import SCHEMA_FILE, json_schema


def write_schema() -> None:
    SCHEMA_FILE.write_text(json.dumps(json_schema(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_schema()
