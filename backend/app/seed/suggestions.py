"""The HR helper's Suggestion in the Seeded history (spec 16).

On the morning of the revert, after running v1 against v2, the Owner has a Suggestion made from
v2's time as the Live Version: its failed Live Verdicts, thumbs-down and low-rated replies, and
the Evaluation Cases it failed in that Run. The Demo model proposes by rule: v2's replies cite
nothing, so it suggests asking for citations in the system prompt and names a Knowledge Base gap
for each failed reply that cited no Chunk. The Agent has an Evaluation Set, so the run checks the
change against v2 on it. Like the seeded Evaluation Runs, the run happens in the seed's own
process, timed by the seed's clock. v1 replaces v2 straight after, so the Suggestion reads as
stale.

The foundation sets the Organisation's Retention Window to two weeks, as an Owner would in
Organisation settings, and the history ends with the Purge, as Beat would run it each night: so
the replies older than two weeks, the Suggestion's oldest evidence among them, read "Text purged"
(ADR-0017), while its change and explanation stay.
"""

from datetime import date, datetime

from fastapi import FastAPI

from app.retention.service import purge_expired
from app.seed import content
from app.seed.client import SeedApi, SeedError
from app.seed.evaluation import runs_in_process


async def retention_window(api: SeedApi) -> None:
    """Sets the Organisation's Retention Window, if it isn't already."""
    if (await api.call("GET", api.path()))["retention_days"] != content.RETENTION_DAYS:
        await api.call(
            "PUT", api.path("retention-window"), body={"retention_days": content.RETENTION_DAYS}
        )


async def suggest(api: SeedApi, project: str, agent: str, start: date, end: date) -> None:
    """Starts a Suggestion run of the Agent's Live Version over the UTC days ``start`` to
    ``end``, and checks it completed."""
    path = api.path("projects", project, "agents", agent, "suggestions")
    with runs_in_process():
        started = await api.call(
            "POST",
            path,
            expect=202,
            body={"range_start": start.isoformat(), "range_end": end.isoformat()},
        )
    finished = await api.call("GET", f"{path}/{started['id']}")
    if finished["status"] != "completed":
        raise SeedError(
            f"The {content.HR_AGENT}'s Suggestion run ended {finished['status']}: "
            f"{finished['error_message']}"
        )


async def purge(app: FastAPI, at: datetime) -> None:
    """The nightly Purge, as of ``at``: Message text older than the Retention Window goes."""
    await purge_expired(app.state.sessionmaker, at)
