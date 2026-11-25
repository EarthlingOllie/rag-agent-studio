"""API seam: the end-to-end path of spec 19 with the offline models (ticket 19-06), as the Studio
end-to-end test drives it on the ``docker compose`` stack (``guidance-demo.spec.ts``).

A fresh Organisation answers with the demo provider's model, which quotes the one Chunk of a
handbook that says what it doesn't cover, and judges with the fake gateway's Claude. Visitors
ask a question the handbook doesn't answer, so the fake judge fails every reply on "answers the
question"; an Owner passes every Review sample item. The fake drafter turns those disagreements
into the one rule the fake judge follows, a check shows agreement rising on the held-out half,
and the saved guidance starts a new Judging setup the next Evaluation Run is judged under.

Nothing is scripted: the default fake adapters answer, judge and draft, as they do in compose.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.evaluation.fake_drafter import PARTIAL_RULE
from tests.agents import create_automatic_agent
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import create_project, upload
from tests.integration.test_evaluation import add_case, evaluated
from tests.integration.test_evaluation_settings import set_evaluation_model, set_repeats
from tests.integration.test_guidance_check import checked
from tests.integration.test_guidance_draft import drafted, drafting
from tests.integration.test_judging_guidance import read_guidance
from tests.integration.test_live_verdict_reviews import reviewed_item
from tests.integration.test_live_verdicts import reply, sampling, served
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_verdict_reviews import next_item

# What the demo model quotes in every reply: a partial answer that says what it doesn't cover.
HANDBOOK = (
    "Everyone gets 25 days of annual leave a year. "
    "This handbook doesn't cover payroll or pensions: ask HR."
)
# Shares no word of five letters or more with the reply, so the fake judge fails it on
# "answers the question" until guidance lets a partial answer pass.
QUESTION = "When is payday?"
REPLIES = 15


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


async def partial_answers(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> dict[str, Any]:
    """The demo model answers, the fake Claude judges every reply of a published Agent over the
    handbook; ``REPLIES`` Visitors ask ``QUESTION``."""
    demo = await added(owner, provider="demo", api_key="demo-no-key-needed")
    chosen = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/default-model",
        json={"credential_id": demo["id"], "model": "demo-chat"},
    )
    assert chosen.status_code == 200, chosen.text
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    judged_by = await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")
    assert judged_by.status_code == 200, judged_by.text
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "handbook.md", f"# Handbook\n\n{HANDBOOK}\n".encode())
    created = await create_automatic_agent(owner, project_id)
    agent = await served(owner, project_id, created["id"])
    await sampling(owner, agent, 100)
    for _ in range(REPLIES):
        await reply(visitor, agent, QUESTION)
    return agent


async def test_a_draft_from_partial_answer_disagreements_raises_agreement_and_is_saved(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await partial_answers(app, owner, visitor)
    reveals = []
    while (item := (await next_item(owner))["item"]) is not None:
        reveals.append((item["check"], (await reviewed_item(owner, item, "pass"))["agreed"]))
    # Every reply cites the handbook (grounding agreed) and fails "answers the question".
    assert (
        sorted(reveals) == [("answers_question", False)] * REPLIES + [("grounding", True)] * REPLIES
    )

    offered = await drafting(owner)
    assert (offered["offered"], offered["disagreements"], offered["sample_reviews"]) == (
        True,
        REPLIES,
        2 * REPLIES,
    )
    draft = await drafted(owner)
    assert draft["status"] == "completed", draft["error_reason"]
    assert draft["draft"]["text"] == PARTIAL_RULE
    assert draft["reviews_read"] == len(draft["draft"]["explanation"][0]["reviews"])

    check = await checked(owner, draft["draft"]["text"])
    assert check["status"] == "completed", check["error_reason"]
    # Every held-out review now agrees: the partial answers pass, as the Owner said.
    assert check["judged"] == check["held_out"] == REPLIES
    assert (check["agreed"], check["false_passes"], check["false_fails"]) == (REPLIES, 0, 0)
    assert check["agreed_before"] < check["agreed"]

    response = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/judging-guidance",
        json={"text": draft["draft"]["text"], "draft_id": draft["id"]},
    )
    assert response.status_code == 200, response.text
    current = (await read_guidance(owner))["current"]
    assert (current["version"], current["source"], current["text"]) == (1, "drafted", PARTIAL_RULE)

    # The next Evaluation Run is judged under the new Judging setup.
    await add_case(owner, agent["project_id"], agent["id"])
    await set_repeats(owner, 1)
    run = (await evaluated(owner, agent["project_id"], agent["id"]))["run"]
    assert (run["judge_provider"], run["judge_model"], run["judging_guidance_version"]) == (
        "anthropic",
        "claude-haiku-4-5",
        1,
    )
