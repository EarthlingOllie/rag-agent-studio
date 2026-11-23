"""Live evaluation in the demo Organisation (spec 15).

The foundation sets the Organisation's Evaluation budget and each seeded Agent's Live sample rate
through the API, as an Owner would in Organisation settings and Embed & limits; the budget comes
first, since a rate above 0 is refused without one.

During the history, the HR helper's Visitor replies are chosen and judged through the normal
sampling path: the widget draws each reply against the Live sample rate and sends the chosen ones'
Live Verdict task. The draws are seeded from the history's fixed random seed, so the same replies
are judged every time, and Celery runs the task eagerly in the seed's process (as for the seeded
Evaluation Runs), so each reply is judged by the Demo model under the seed's clock, minutes after
it was given.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from app.evaluation.live import seed_draws
from app.seed import content
from app.seed.client import SeedApi
from app.seed.evaluation import runs_in_process


async def budget(api: SeedApi) -> None:
    """Sets the Organisation's Evaluation budget, if it isn't already."""
    path = api.path("evaluation-budget")
    current = (await api.call("GET", path))["evaluation_budget_usd"]
    wanted = content.EVALUATION_BUDGET_USD
    if current is None or Decimal(current) != wanted:
        await api.call("PUT", path, body={"evaluation_budget_usd": str(wanted)})


async def sample_rates(api: SeedApi, project: str, agents: dict[str, Any]) -> None:
    """Sets each seeded Agent's Live sample rate where it differs (0 for those not sampled)."""
    for wanted in content.AGENTS:
        path = api.path(
            "projects", project, "agents", agents[wanted.name]["id"], "operational-settings"
        )
        rate = content.LIVE_SAMPLE_RATES.get(wanted.name, 0)
        if (await api.call("GET", path))["live_sample_rate"] != rate:
            await api.call("PATCH", path, body={"live_sample_rate": rate})


async def set_up(api: SeedApi, project: str, agents: dict[str, Any]) -> None:
    await budget(api)
    await sample_rates(api, project, agents)


def seed_sampling(random_seed: int) -> None:
    """Seeds the Live sample rate's draws, so the history judges the same replies each time."""
    seed_draws(random_seed)


@contextmanager
def judged_in_process() -> Iterator[None]:
    """Replies chosen meanwhile are judged in this process, under the seed's clock."""
    with runs_in_process():
        yield
