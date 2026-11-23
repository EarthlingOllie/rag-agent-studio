"""Live suite: one real Suggestion run (spec 16). The demo Organisation is seeded with a real
Provider Credential as its Default Model, as ``make seed`` does with
``SEED_CREDENTIAL_PROVIDER`` (anthropic or openai), ``SEED_CREDENTIAL_API_KEY`` and an optional
``SEED_CREDENTIAL_MODEL``, so the real model proposes (the Evaluation Model falls back to the
Default Model). An Editor starts a Suggestion run of the seeded HR helper over the default range,
the last 14 days: the seeded evidence of its Live Version (failed Live Verdicts, thumbs-down and
low-rated replies, and the Evaluation Cases it failed in the seeded Run), plus one reply a Visitor
gives a thumbs-down now, so there is always evidence to read.

It asserts only that the real model's output validates: the run completes (an answer off the
schema fails it), proposed by the real model, with every change to a setting a Suggestion may
change and citing evidence the run gave it, and its proposing Cost frozen. What it proposes is the
model's to decide.

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

QUESTION = "Can I carry leave over to next year?"
# The settings a Suggestion may change (spec 16).
SETTINGS = {
    "behaviour.system_prompt",
    "retrieval.top_k",
    "retrieval.minimum_score",
    "retrieval.hybrid_weighting",
}


@pytest.fixture
def real() -> RealCredential:
    found = real_credential_from_env(os.environ)
    if found is None:
        skip_or_fail(
            "No real Provider Credential: set SEED_CREDENTIAL_PROVIDER (anthropic or openai) "
            "and SEED_CREDENTIAL_API_KEY to propose a real Suggestion."
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


async def test_a_real_model_proposes_a_valid_suggestion_for_the_seeded_hr_helper(
    app: FastAPI, new_client: ClientFactory, real: RealCredential
) -> None:
    await erase_demo(app)
    await seed(app, DEFAULT_ASSETS, real)
    editor = await signed_in(new_client, content.EDITOR)
    project = (await demo_project(editor))["id"]
    agents = {a["name"]: a for a in await get(editor, "projects", project, "agents")}
    hr = agents[content.HR_AGENT]

    # A Visitor gives a reply of the Live Version a thumbs-down today.
    visitor: httpx.AsyncClient = await new_client()
    token = await conversation_token(visitor, hr["public_id"])
    answered = await send(visitor, hr["public_id"], token, QUESTION)
    assert answered.status_code == 200, answered.text
    (done,) = [data for event, data in parse_sse(answered.text) if event == "done"]
    voted = await visitor.put(
        f"/api/widget/agents/{hr['public_id']}/messages/{done['message_id']}/feedback",
        json={"rating": "down"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert voted.status_code == 200, voted.text

    suggestions = (
        f"/api/organisations/{editor.organisation_id}/projects/{project}/agents/{hr['id']}"
        "/suggestions"
    )
    # Celery runs the task eagerly in the test's process, so the run has finished on return.
    started = await editor.client.post(suggestions, json={})
    assert started.status_code == 202, started.text
    suggestion = (await editor.client.get(f"{suggestions}/{started.json()['id']}")).json()

    assert suggestion["status"] == "completed", suggestion["error_message"]
    assert suggestion["evidence_total"] >= 1
    assert (suggestion["model_provider"], suggestion["model_name"]) == (
        real.provider.value,
        real.model,
    )
    assert suggestion["outcome"] in ("changes", "gaps_only", "no_change")
    assert suggestion["explanation"]
    given = {e["id"] for e in suggestion["evidence"]}
    for change in suggestion["changes"]:
        assert change["path"] in SETTINGS
        assert change["suggested_value"] != change["base_value"]
        assert change["explanation"]
        assert set(change["evidence_ids"]) <= given
        if change["path"] != "behaviour.system_prompt":
            assert change["evidence_ids"]
    for gap in suggestion["gaps"]:
        assert gap["topic"]
        assert set(gap["evidence_ids"]) <= given
    assert (suggestion["outcome"] == "changes") == bool(suggestion["changes"])
    # Proposing's Cost is frozen when it was spent.
    assert suggestion["cost"]["proposing_usd"] is not None
    assert Decimal(suggestion["cost"]["proposing_usd"]) > 0
