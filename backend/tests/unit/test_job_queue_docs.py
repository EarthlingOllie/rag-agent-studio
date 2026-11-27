"""The development guide says which queue each job goes to, and says it right (ticket 22-08).

``docs/development.md`` has a table, under "Which queue each job goes to", with one row per
Celery task: its name in backticks in the first column and its queue (``general`` or ``runs``)
in the last. Every task the worker registers must have a row, and the row must name the queue
``queue_for`` routes it to, so the guide can't drift from the routing.
"""

import re
from pathlib import Path

from app.worker.celery_app import celery_app, queue_for

GUIDE = Path(__file__).resolve().parents[3] / "docs/development.md"
HEADING = "### Which queue each job goes to"
ROW = re.compile(r"^\|\s*`(?P<task>[a-z_.]+)`\s*\|.*\|\s*(?P<queue>general|runs)\s*\|\s*$")


def _documented_queues() -> dict[str, str]:
    text = GUIDE.read_text()
    assert HEADING in text, f"{GUIDE.name} has no '{HEADING}' section"
    section = text.split(HEADING, 1)[1].split("\n#", 1)[0]
    rows = (ROW.match(line) for line in section.splitlines())
    return {row["task"]: row["queue"] for row in rows if row}


def _registered_tasks() -> set[str]:
    celery_app.loader.import_default_modules()
    return {name for name in celery_app.tasks if not name.startswith("celery.")}


def test_the_guide_lists_every_job_the_worker_runs() -> None:
    assert set(_documented_queues()) == _registered_tasks()


def test_the_guide_names_the_queue_each_job_is_routed_to() -> None:
    documented = _documented_queues()

    assert documented == {task: queue_for(task) for task in documented}
    assert {task for task, queue in documented.items() if queue == "runs"} == {
        "evaluation.run",
        "suggestions.run",
    }
