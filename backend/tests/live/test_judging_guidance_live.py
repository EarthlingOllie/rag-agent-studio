"""Live suite: one real draft and check of Judging guidance (spec 19, ticket 19-06).

A fresh Organisation answers with the demo provider's model (offline and deterministic: every
reply quotes the one Chunk of a handbook that says what it doesn't cover) and judges with a real
Provider Credential as its Evaluation Model, read from ``SEED_CREDENTIAL_PROVIDER`` (anthropic or
openai), ``SEED_CREDENTIAL_API_KEY`` and an optional ``SEED_CREDENTIAL_MODEL``, as ``make seed``
does. Visitors ask ``REPLIES`` questions the handbook doesn't answer; the real model judges each
reply (eagerly, in the test's process). An Owner then works through the small Review sample this
seeds, differing from the real model on every item, and the drafting thresholds are lowered to
fit it, so a real draft reads a handful of disagreements and a real check re-judges the held-out
half.

It asserts only that the real model's output validates: the draft completes with guidance within
the limit and an explanation citing the reviews it was given, the check re-judges every held-out
review and counts each one once, and both Costs are frozen. What it drafts, and whether the
check raises agreement, is the model's to decide.

It needs the compose Postgres and Redis, like the integration tests, and the provider's API.
Run with ``make test-live`` (nightly in the ``live`` workflow); without a credential in the
environment it is skipped with the reason, unless ``LIVE_REQUIRE_MODELS=1``."""

import os
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.evaluation import guidance_draft
from app.evaluation.models import GUIDANCE_MAX
from app.seed.runner import RealCredential, real_credential_from_env
from tests.agents import create_automatic_agent
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import create_project, upload
from tests.integration.test_evaluation_settings import set_evaluation_model
from tests.integration.test_guidance_check import checked
from tests.integration.test_guidance_demo_path import HANDBOOK, QUESTION
from tests.integration.test_guidance_draft import drafted, drafting
from tests.integration.test_live_verdict_reviews import reviewed_item
from tests.integration.test_live_verdicts import reply, sampling, served
from tests.integration.test_provider_credentials import added
from tests.integration.test_verdict_reviews import next_item
from tests.live.models import skip_or_fail

pytestmark = pytest.mark.live

# Each reply gives two Review sample items (grounding, answers the question).
REPLIES = 4
PASS_REASON = "It says what the handbook doesn't cover and who to ask: that answers it here."
FAIL_REASON = "It quotes the handbook but never answers what was asked."


@pytest.fixture
def real() -> RealCredential:
    found = real_credential_from_env(os.environ)
    if found is None:
        skip_or_fail(
            "No real Provider Credential: set SEED_CREDENTIAL_PROVIDER (anthropic or openai) "
            "and SEED_CREDENTIAL_API_KEY to draft and check real Judging guidance."
        )
    assert found is not None
    return found


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch, real: RealCredential) -> pytest.MonkeyPatch:
    """Real models and real credential checks; the demo model answers the Visitors."""
    settings_env.setenv("MODEL_GATEWAY", "live")
    settings_env.setenv("CREDENTIAL_VERIFIER", "live")
    # Drafting from the small seeded set: every review disagrees, so a draft reads about half.
    settings_env.setattr(guidance_draft, "DRAFT_DISAGREEMENTS", REPLIES)
    settings_env.setattr(guidance_draft, "DRAFT_SAMPLE_REVIEWS", 2 * REPLIES)
    return settings_env


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


async def test_a_real_model_drafts_and_checks_valid_guidance_from_seeded_reviews(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, real: RealCredential
) -> None:
    demo = await added(owner, provider="demo", api_key="demo-no-key-needed")
    chosen = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/default-model",
        json={"credential_id": demo["id"], "model": "demo-chat"},
    )
    assert chosen.status_code == 200, chosen.text
    credential = await added(owner, provider=real.provider.value, api_key=real.api_key)
    judged_by = await set_evaluation_model(owner, credential["id"], real.model)
    assert judged_by.status_code == 200, judged_by.text
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "handbook.md", f"# Handbook\n\n{HANDBOOK}\n".encode())
    created = await create_automatic_agent(owner, project_id)
    agent = await served(owner, project_id, created["id"])
    await sampling(owner, agent, 100)
    for _ in range(REPLIES):
        await reply(visitor, agent, QUESTION)

    # The Owner differs from the real model on every item: a pass where it failed, else a fail.
    reviewed = 0
    while (item := (await next_item(owner))["item"]) is not None:
        if (await reviewed_item(owner, item, "pass", PASS_REASON))["agreed"]:
            await reviewed_item(owner, item, "fail", FAIL_REASON)
        reviewed += 1
    assert reviewed == 2 * REPLIES
    offered = await drafting(owner)
    assert offered["offered"], offered["missing"]

    draft = await drafted(owner)

    assert draft["status"] == "completed", draft["error_reason"]
    proposal = draft["draft"]
    assert 0 < len(proposal["text"]) <= GUIDANCE_MAX
    assert proposal["explanation"]
    for part in proposal["explanation"]:
        assert part["part"]
        assert part["reviews"]
    assert draft["reviews_read"] == REPLIES
    assert Decimal(draft["cost_usd"]) > 0

    check = await checked(owner, proposal["text"])

    assert check["status"] == "completed", check["error_reason"]
    assert check["held_out"] == REPLIES
    assert check["judged"] + check["left_out"] == check["held_out"]
    assert check["agreed"] + check["false_passes"] + check["false_fails"] == check["judged"]
    # Every held-out review disagreed with the real model as it judged without guidance.
    assert check["agreed_before"] == 0
    assert Decimal(check["cost_usd"]) > 0
