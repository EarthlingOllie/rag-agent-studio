"""Live suite: one real Agentic reply (spec 13). The demo Organisation is seeded with a real
Provider Credential as its Default Model, as ``make seed`` does with ``SEED_CREDENTIAL_PROVIDER``
(anthropic or openai), ``SEED_CREDENTIAL_API_KEY`` and an optional ``SEED_CREDENTIAL_MODEL``.
The seeded Agentic Agent, the Product FAQ, is asked a question in the Playground. The real model
must search the seed Knowledge Base with Knowledge Search at least once and cite a Chunk a
Search gave it.

It needs the compose Postgres and Redis, like the integration tests, and the provider's API.
Run with ``make test-live``; without a credential in the environment it is skipped with the
reason, unless ``LIVE_REQUIRE_MODELS=1``."""

import os
from typing import Any

import pytest
from fastapi import FastAPI

from app.credentials.registry import PROVIDERS
from app.seed import content
from app.seed.__main__ import DEFAULT_ASSETS
from app.seed.runner import RealCredential, erase_demo, real_credential_from_env, seed
from tests.conftest import ClientFactory
from tests.integration.test_agentic_retrieval import asked
from tests.integration.test_seed import demo_project, get, signed_in
from tests.live.models import skip_or_fail

pytestmark = [pytest.mark.live, pytest.mark.usefixtures("quiet_seed_history")]

QUESTION = "Can I return a jar of honey, and how long do I have to send it back?"


@pytest.fixture
def real() -> RealCredential:
    found = real_credential_from_env(os.environ)
    if found is None:
        skip_or_fail(
            "No real Provider Credential: set SEED_CREDENTIAL_PROVIDER (anthropic or openai) "
            "and SEED_CREDENTIAL_API_KEY to make a real Agentic reply."
        )
    assert found is not None
    return found


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch, real: RealCredential) -> pytest.MonkeyPatch:
    """Real models and real credential checks; Docling reads the seed's Documents (Markdown,
    DOCX and PPTX need no models). Embeddings stay the deterministic fake: the Hybrid search's
    keyword half finds the Chunks."""
    settings_env.setenv("MODEL_GATEWAY", "live")
    settings_env.setenv("CREDENTIAL_VERIFIER", "live")
    settings_env.setenv("DOCUMENT_CONVERTER", "docling")
    settings_env.delenv("DEMO_SHOP_ORIGIN", raising=False)
    return settings_env


async def test_a_real_model_searches_the_seed_knowledge_base_and_cites_a_chunk(
    app: FastAPI, new_client: ClientFactory, real: RealCredential
) -> None:
    await erase_demo(app)
    report = await seed(app, DEFAULT_ASSETS, real)
    assert report.default_model.endswith(f"(Northwind {PROVIDERS[real.provider].name})")
    editor = await signed_in(new_client, content.EDITOR)
    project = await demo_project(editor)
    agents = {a["name"]: a for a in await get(editor, "projects", project["id"], "agents")}
    faq = agents[content.SHOP_AGENT]
    assert faq["draft"]["retrieval"]["mode"] == "agentic"

    events, trace = await asked(editor, project["id"], faq["id"], QUESTION)

    kinds = [kind for kind, _ in events]
    assert "error" not in kinds, events
    searched = [data for kind, data in events if kind == "search"]
    assert searched, f"The model answered without searching: {events}"
    assert all(data["query"].strip() for data in searched)
    done: dict[str, Any] = events[-1][1]
    assert done["fallback"] is False
    assert trace["search_count"] == len(searched) >= 1
    assert (trace["fallback"], trace["automatic_fallback"]) == (False, False)
    given = {
        chunk["chunk_id"]
        for search in trace["searches"]
        for chunk in search["chunks"]
        if chunk["rank"] is not None
    }
    cited = [chunk for search in trace["searches"] for chunk in search["chunks"] if chunk["cited"]]
    assert cited, f"The answer cites no Chunk: {events}"
    assert {chunk["chunk_id"] for chunk in cited} <= given
    citations = [data for kind, data in events if kind == "citation"]
    assert citations, events
    answer = "".join(data["text"] for kind, data in events if kind == "token")
    assert answer.strip()
