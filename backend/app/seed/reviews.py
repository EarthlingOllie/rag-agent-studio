"""Verdict review in the demo Organisation (spec 18).

Once the history has played, and after its nightly Purge (so no review's reason is cleared), the
Owner and the Editor take turns on the Review sample, through the API as the Studio's Review
sample page does: each draws the next item, gives a pass or fail blind, and sees the reveal. They
review ``content.SAMPLE_REVIEWS`` items, drawn from the HR helper's judged Run Verdicts and Live
Verdict checks with the draws seeded from the history's fixed random seed.

The seed can't judge an answer's meaning, so the reviewers agree with the Demo model except on a
few items: about one in every ``content.FALSE_PASS_EVERY`` reviews they give a fail, and when the
reveal shows the Demo model passed it (a false pass) they save why, as the reveal's "Why you
differ" form does. Otherwise they give a pass, and when the reveal shows a fail they review the
item again with a fail, which replaces the first review as the Review sample allows. So the
agreement card shows ``content.FALSE_PASSES`` false passes and no false fails.
"""

from typing import Any

from app.evaluation.reviews import seed_draws
from app.seed import content
from app.seed.client import SeedApi

PASS, FAIL = "pass", "fail"


def _target(item: dict[str, Any]) -> dict[str, Any]:
    if item["verdict_id"] is not None:
        return {"verdict_id": item["verdict_id"]}
    return {"live_verdict_id": item["live_verdict_id"], "check": item["check"]}


async def review_sample(reviewers: list[SeedApi], random_seed: int) -> None:
    """Up to ``content.SAMPLE_REVIEWS`` Review sample reviews, the reviewers taking turns; fewer
    when the sample runs out first."""
    seed_draws(random_seed)
    false_passes = 0
    for number in range(content.SAMPLE_REVIEWS):
        api = reviewers[number % len(reviewers)]
        drawn = await api.call("GET", api.path("review-sample", "next"))
        item = drawn["item"]
        if item is None:
            return
        reviews = api.path("review-sample", "reviews")
        due = false_passes < min(content.FALSE_PASSES, number // content.FALSE_PASS_EVERY + 1)
        target = _target(item)
        given = FAIL if due else PASS
        reveal = await api.call("POST", reviews, body={**target, "outcome": given})
        if reveal["agreed"]:
            continue
        if due:
            reason = content.FALSE_PASS_REASONS[item["check"]]
            await api.call("POST", reviews, body={**target, "outcome": FAIL, "reason": reason})
            false_passes += 1
        else:
            await api.call("POST", reviews, body={**target, "outcome": FAIL})
