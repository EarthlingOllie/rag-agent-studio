"""Live suite: one real Live Verdict (spec 15). The demo Organisation is seeded with a real
Provider Credential as its Default Model, as ``make seed`` does with
``SEED_CREDENTIAL_PROVIDER`` (anthropic or openai), ``SEED_CREDENTIAL_API_KEY`` and an optional
``SEED_CREDENTIAL_MODEL``. The seed gives the Organisation its Evaluation budget and the HR
helper its Live sample rate; the Owner raises the rate to 100% and a Visitor asks the seeded HR
helper a question through the widget. The real model answers and, as the Evaluation Model falls
back to the Default Model, judges the reply in the background (eagerly, in the test's process).
Its Live Verdict must be judged by the real model, with both checks and the model's own reasons,
its Cost frozen and counted against the budget.

It needs the compose Postgres and Redis, like the integration tests, and the provider's API.
Run with ``make test-live`` (nightly in the ``live`` workflow); without a credential in the
environment it is skipped with the reason, unless ``LIVE_REQUIRE_MODELS=1``."""

import os
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.seed import content
from app.seed.__main__ import DEFAULT_ASSETS
from app.seed.runner import RealCredential, erase_demo, real_credential_from_env, seed
from tests.agents import parse_sse
from tests.conftest import ClientFactory
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_seed import demo_project, get, signed_in
from tests.live.models import skip_or_fail

pytestmark = [pytest.mark.live, pytest.mark.usefixtures("quiet_seed_history")]

QUESTION = "How many days of annual leave do I get?"


@pytest.fixture
def real() -> RealCredential:
    found = real_credential_from_env(os.environ)
    if found is None:
        skip_or_fail(
            "No real Provider Credential: set SEED_CREDENTIAL_PROVIDER (anthropic or openai) "
            "and SEED_CREDENTIAL_API_KEY to judge a real Live Verdict."
        )
    assert found is not None
    return found


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch, real: RealCredential) -> pytest.MonkeyPatch:
    """Real models and real credential checks; Docling reads the seed's Documents. Embeddings
    stay the deterministic fake: the Hybrid search's keyword half finds the Chunks."""
    settings_env.setenv("MODEL_GATEWAY", "live")
    settings_env.setenv("CREDENTIAL_VERIFIER", "live")
    settings_env.setenv("DOCUMENT_CONVERTER", "docling")
    settings_env.delenv("DEMO_SHOP_ORIGIN", raising=False)
    return settings_env


async def test_a_real_model_judges_a_visitor_reply_of_the_seeded_hr_helper(
    app: FastAPI, new_client: ClientFactory, real: RealCredential
) -> None:
    await erase_demo(app)
    await seed(app, DEFAULT_ASSETS, real)
    owner = await signed_in(new_client, content.OWNER)
    project = (await demo_project(owner))["id"]
    agents = {a["name"]: a for a in await get(owner, "projects", project, "agents")}
    hr = agents[content.HR_AGENT]
    settings = f"/api/organisations/{owner.organisation_id}/projects/{project}/agents/{hr['id']}"
    raised = await owner.client.patch(
        f"{settings}/operational-settings", json={"live_sample_rate": 100}
    )
    assert raised.status_code == 200, raised.text

    visitor: httpx.AsyncClient = await new_client()
    token = await conversation_token(visitor, hr["public_id"])
    answered = await send(visitor, hr["public_id"], token, QUESTION)
    assert answered.status_code == 200, answered.text
    (done,) = [data for event, data in parse_sse(answered.text) if event == "done"]

    (conversation,) = (
        await owner.client.get(
            f"/api/organisations/{owner.organisation_id}/projects/{project}/conversations",
            params={"agent_id": hr["id"], "playground": "false"},
        )
    ).json()["items"]
    trace = await get(
        owner,
        "projects",
        project,
        "conversations",
        conversation["id"],
        "messages",
        done["message_id"],
        "trace",
    )
    verdict = trace["live_verdict"]
    assert verdict is not None
    assert verdict["status"] == "judged", verdict["error_reason"]
    assert (verdict["judge_provider"], verdict["judge_model"]) == (real.provider.value, real.model)
    for check in (verdict["grounded"], verdict["answers_question"]):
        assert check["outcome"] in ("pass", "fail")
        assert check["reason"]
        assert not check["reason"].startswith("Fake judge")
    # The handbook answers the question, so a real judge finds the reply answers it.
    assert verdict["answers_question"]["outcome"] == "pass", verdict["answers_question"]["reason"]
    assert verdict["passed"] == (
        verdict["grounded"]["outcome"] == verdict["answers_question"]["outcome"] == "pass"
    )
    assert verdict["input_tokens"] > 0
    assert verdict["output_tokens"] > 0
    # The judge's Cost is frozen on the Live Verdict and counted against the month's budget.
    assert verdict["cost_usd"] is not None
    assert Decimal(verdict["cost_usd"]) > 0
    budget = await get(owner, "evaluation-budget")
    assert Decimal(budget["spent_usd"]) == Decimal(verdict["cost_usd"])
