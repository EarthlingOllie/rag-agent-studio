"""The HR helper's Evaluation Set and its two Runs in the Seeded history (spec 14).

On the morning of the revert the Owner builds the set: a case added from each of a few Messages
Visitors gave a thumbs down (through the "prefill from Message" read, as the Conversations
viewer's "Add to Evaluation Set" does), and the rest written. The Owner then runs v1 against v2,
whose Regressions explain the revert. After v3 is published the Editor runs the Draft against it.

The Runs are judged by the Demo model (the Default Model during the history). They run in the
seed's own process, so the Run job is timed by the seed's clock like the rest of the history:
while the seed starts them, Celery runs tasks eagerly.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.seed import content
from app.seed.client import SeedApi, SeedError
from app.worker.celery_app import celery_app


@contextmanager
def runs_in_process() -> Iterator[None]:
    """Celery runs the tasks sent meanwhile in this process, then goes back to how it was."""
    before = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        yield
    finally:
        celery_app.conf.task_always_eager = before


async def _downvoted(api: SeedApi, project: str, agent: str, evaluation: str) -> set[str]:
    """Up to ``CASES_FROM_MESSAGES`` questions the Agent's thumbs-down replies answered, newest
    first, each read through the "prefill from Message" read."""
    found: set[str] = set()
    conversations = await api.call(
        "GET",
        api.path("projects", project, "conversations")
        + f"?agent_id={agent}&feedback=down&playground=false&page_size=100",
    )
    for conversation in conversations["items"]:
        read = await api.call(
            "GET", api.path("projects", project, "conversations", conversation["id"])
        )
        for message in read["messages"]:
            if len(found) == content.CASES_FROM_MESSAGES:
                return found
            if (message["feedback"] or {}).get("rating") == "down":
                prefill = await api.call("GET", f"{evaluation}/messages/{message['id']}/prefill")
                found.add(prefill["question"])
    return found


async def build_set(api: SeedApi, project: str, agent: str) -> None:
    """The HR helper's Evaluation Set, in ``content.EVALUATION_CASES`` order."""
    evaluation = api.path("projects", project, "agents", agent, "evaluation")
    documents = {
        d["name"]: d["id"]
        for d in await api.call("GET", api.path("projects", project, "documents"))
    }
    downvoted = await _downvoted(api, project, agent, evaluation)
    for case in content.EVALUATION_CASES:
        sources = []
        if case.expected_source is not None:
            filename, passage = case.expected_source
            sources.append({"document_id": documents[filename], "passage": passage})
        await api.call(
            "POST",
            f"{evaluation}/cases",
            expect=201,
            body={
                "question": case.question,
                "reference_answer": case.reference_answer,
                "expected_sources": sources,
                "expect_fallback": case.expect_fallback,
                "source": "from_message" if case.question in downvoted else "written",
            },
        )


async def run(api: SeedApi, project: str, agent: str, sides: list[dict[str, Any]] | None) -> None:
    """Starts a Run (the Live Version against the Draft when ``sides`` is None) and checks it
    completed."""
    evaluation = api.path("projects", project, "agents", agent, "evaluation")
    with runs_in_process():
        started = await api.call("POST", f"{evaluation}/runs", expect=202, body={"sides": sides})
    finished = await api.call("GET", f"{evaluation}/runs/{started['id']}")
    if finished["status"] != "completed":
        raise SeedError(
            f"The {content.HR_AGENT}'s Evaluation Run ended {finished['status']}: "
            f"{finished['error_message']}"
        )


async def version_sides(api: SeedApi, project: str, agent: str, *numbers: int) -> list[Any]:
    """The Run sides of the Agent's Versions with these numbers, in order."""
    versions = await api.call("GET", api.path("projects", project, "agents", agent, "versions"))
    ids = {v["number"]: v["id"] for v in versions["versions"]}
    return [{"kind": "version", "version_id": ids[number]} for number in numbers]
