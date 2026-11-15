"""Live suite: one real Evaluation Run (spec 14). The demo Organisation is seeded with a real
Provider Credential as its Default Model, as ``make seed`` does with ``SEED_CREDENTIAL_PROVIDER``
(anthropic or openai), ``SEED_CREDENTIAL_API_KEY`` and an optional ``SEED_CREDENTIAL_MODEL``, so
the real model answers and, as the Evaluation Model falls back to the Default Model, judges.

An Editor makes a new Agent over the seed Knowledge Base's HR Documents, with three cases, one per
expectation kind (a Reference answer, an Expected source in the staff handbook, Expect Fallback
Text), and runs its Draft alone, one repeat each. The Run must complete with every case answered,
judged by the real model with its own reasons, and the Reference answer must pass.

It needs the compose Postgres and Redis, like the integration tests, and the provider's API.
Run with ``make test-live`` (nightly in the ``live`` workflow); without a credential in the
environment it is skipped with the reason, unless ``LIVE_REQUIRE_MODELS=1``."""

import os
from typing import Any

import pytest
from fastapi import FastAPI

from app.seed import content
from app.seed.__main__ import DEFAULT_ASSETS
from app.seed.runner import RealCredential, erase_demo, real_credential_from_env, seed
from tests.conftest import ClientFactory, SignedUpMember
from tests.integration.test_seed import demo_project, get, signed_in
from tests.live.models import skip_or_fail

pytestmark = [pytest.mark.live, pytest.mark.usefixtures("quiet_seed_history")]

REFERENCE = "How many days of annual leave do I get?"
EXPECTED_SOURCE = "How far ahead do I have to book leave?"
FALLBACK = "What's the Wi-Fi password in the office?"
CASES: list[dict[str, Any]] = [
    {"question": REFERENCE, "reference_answer": "Everyone gets 25 days of annual leave a year."},
    {
        "question": EXPECTED_SOURCE,
        "expected_sources": [{"passage": "Book leave in the HR portal at least two weeks ahead"}],
    },
    {"question": FALLBACK, "expect_fallback": True},
]
# The kinds of Verdict each case must get: its expectation, and grounding unless it is the
# Fallback Text (which skips grounding when the answer is the Fallback Text).
KINDS = {REFERENCE: "reference_answer", EXPECTED_SOURCE: "expected_source", FALLBACK: "fallback"}


@pytest.fixture
def real() -> RealCredential:
    found = real_credential_from_env(os.environ)
    if found is None:
        skip_or_fail(
            "No real Provider Credential: set SEED_CREDENTIAL_PROVIDER (anthropic or openai) "
            "and SEED_CREDENTIAL_API_KEY to run a real Evaluation Run."
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


async def call(member: SignedUpMember, method: str, expect: int, *parts: str, body: Any) -> Any:
    path = "/".join(["/api/organisations", member.organisation_id, *parts])
    response = await member.client.request(method, path, json=body)
    assert response.status_code == expect, response.text
    return response.json()


async def test_a_real_model_answers_and_judges_one_case_of_each_expectation_kind(
    app: FastAPI, new_client: ClientFactory, real: RealCredential
) -> None:
    await erase_demo(app)
    await seed(app, DEFAULT_ASSETS, real)
    owner = await signed_in(new_client, content.OWNER)
    await call(owner, "PUT", 200, "evaluation-repeats", body={"repeats": 1})
    editor = await signed_in(new_client, content.EDITOR)
    project = (await demo_project(editor))["id"]
    tags = {t["name"]: t["id"] for t in await get(editor, "projects", project, "tags")}
    documents = {d["name"]: d["id"] for d in await get(editor, "projects", project, "documents")}
    agent = await call(
        editor, "POST", 201, "projects", project, "agents", body={"name": "Evaluation live check"}
    )
    agent_path = ("projects", project, "agents", agent["id"])
    draft = agent["draft"]
    retrieval = {**draft["retrieval"], "tag_ids": [tags[content.HR]], "mode": "automatic"}
    await call(editor, "PUT", 200, *agent_path, "draft", body={**draft, "retrieval": retrieval})
    for case in CASES:
        sources = [
            {**source, "document_id": documents[content.HANDBOOK]}
            for source in case.get("expected_sources", [])
        ]
        body = {**case, "expected_sources": sources}
        await call(editor, "POST", 201, *agent_path, "evaluation", "cases", body=body)

    started = await call(editor, "POST", 202, *agent_path, "evaluation", "runs", body=None)

    results = await get(editor, *agent_path, "evaluation", "runs", started["id"], "results")
    run = results["run"]
    assert run["status"] == "completed", run["error_message"]
    assert (run["judge_provider"], run["judge_model"]) == (real.provider.value, real.model)
    assert [(s["kind"], s["model_name"]) for s in run["sides"]] == [("draft", real.model)]
    by_question = {case["question"]: case for case in results["cases"]}
    assert set(by_question) == set(KINDS)
    for question, kind in KINDS.items():
        (result,) = by_question[question]["results"]
        assert result["status"] == "answered", result["error_reason"]
        assert result["answer"].strip()
        verdicts = {v["kind"]: v for v in result["verdicts"]}
        assert kind in verdicts, verdicts
        assert verdicts[kind]["outcome"] in ("pass", "fail")
        judged = [v for v in verdicts.values() if v["kind"] in ("reference_answer", "grounding")]
        assert all(v["reason"] and not v["reason"].startswith("Fake judge") for v in judged)
    (leave,) = by_question[REFERENCE]["results"]
    reference = next(v for v in leave["verdicts"] if v["kind"] == "reference_answer")
    assert reference["outcome"] == "pass", reference["reason"]
    assert any(v["kind"] == "grounding" for v in leave["verdicts"])
