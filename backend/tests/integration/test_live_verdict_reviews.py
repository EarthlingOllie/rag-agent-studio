"""API seam and task seam: Live Verdict checks in the Review sample, and their retention (spec 18,
ticket 18-03). Both checks of a judged Live Verdict (grounded, answers the question) are served
blind with the reply's Remembered turns; the Purge, and deleting a Conversation, clear the reason
on their reviews and stamp them purged-at, while the outcomes stay and agreement is unchanged.

Live Verdicts come from spec 15's flow: a Visitor reply streamed by a scripted ``FunctionModel``,
judged in the background by the same model's structured output, eagerly. Here reviews' reason
and purged-at stamp are read from the table; ``test_reviews_where_shown`` reads them in the
Trace.
"""

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select

from app.evaluation.review_models import VerdictReview
from tests.agents import AUTOMATIC, save_draft
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import conversations_path, listed
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_evaluation_settings import set_evaluation_model
from tests.integration.test_live_verdict_context import conversation, judge_now
from tests.integration.test_live_verdict_context import held_back as held_back
from tests.integration.test_live_verdicts import judged, live_agent, sampling, scripted
from tests.integration.test_playground import ANSWER, LEAVE
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_retention import purge, set_window
from tests.integration.test_verdict_reviews import agreement, next_item, sample_path
from tests.integration.test_version_metrics import roll_up

GROUNDED = {"passed": True, "reason": "Ada's 25 days are cited from the leave policy."}
ANSWERS = {"passed": False, "reason": "Ada asked about part-timers; it answers for everyone."}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def review_item(
    member: SignedUpMember, item: dict[str, Any], outcome: str, reason: str | None = None
) -> httpx.Response:
    """Reviews a served item, whichever its target."""
    return await member.client.post(
        sample_path(member, "reviews"),
        json={
            "verdict_id": item["verdict_id"],
            "live_verdict_id": item["live_verdict_id"],
            "check": item["check"],
            "outcome": outcome,
            "reason": reason,
        },
    )


async def reviewed_item(
    member: SignedUpMember, item: dict[str, Any], outcome: str, reason: str | None = None
) -> dict[str, Any]:
    response = await review_item(member, item, outcome, reason)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def drained(member: SignedUpMember, outcome: str = "pass") -> list[dict[str, Any]]:
    """Every item the sample serves, each reviewed with ``outcome`` so the next one is served."""
    served: list[dict[str, Any]] = []
    while (item := (await next_item(member))["item"]) is not None:
        served.append(item)
        await reviewed_item(member, item, outcome)
    return served


async def remembering(app: FastAPI, owner: SignedUpMember, turns: int) -> dict[str, Any]:
    """A live Agent whose published Version remembers ``turns`` turns, every reply sampled and
    judged with ``GROUNDED`` and ``ANSWERS``."""
    scripted(app, judgement=judged(GROUNDED, ANSWERS))
    agent = await live_agent(app, owner)
    draft = {"retrieval": AUTOMATIC, "behaviour": {"remembered_turns": turns}}
    saved = await save_draft(owner, agent["project_id"], agent["id"], draft)
    assert saved.status_code == 200, saved.text
    await published(owner, agent["project_id"], agent["id"])
    await sampling(owner, agent, 100)
    return agent


async def reviews_of(app: FastAPI, member: SignedUpMember) -> list[VerdictReview]:
    """The Organisation's reviews, oldest first."""
    async with app.state.sessionmaker() as session:
        return list(
            await session.scalars(
                select(VerdictReview)
                .where(VerdictReview.organisation_id == uuid.UUID(member.organisation_id))
                .order_by(VerdictReview.reviewed_at)
            )
        )


# The Review sample


async def test_both_checks_of_a_live_verdict_are_served_blind_with_its_remembered_turns(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await remembering(app, owner, 1)
    await conversation(visitor, agent, "How much annual leave?", "What about part-timers?")
    by_question: dict[str, list[dict[str, Any]]] = {}

    while (found := await next_item(editor))["item"] is not None:
        item = found["item"]
        # Blind: nothing of the Evaluation Model's outcome or reason is served.
        assert "Ada" not in str(found)
        assert "outcome" not in item
        by_question.setdefault(item["question"], []).append(item)
        reveal = await reviewed_item(editor, item, "pass")
        expected = GROUNDED if item["check"] == "grounding" else ANSWERS
        assert reveal["evaluation_model_reason"] == expected["reason"]
        assert reveal["evaluation_model_outcome"] == ("pass" if expected["passed"] else "fail")
        assert reveal["agreed"] is expected["passed"]

    first, follow_up = by_question["How much annual leave?"], by_question["What about part-timers?"]
    for items in (first, follow_up):
        assert sorted(i["check"] for i in items) == ["answers_question", "grounding"]
        assert len({i["live_verdict_id"] for i in items}) == 1
    item = follow_up[0]
    assert item["verdict_id"] is None
    assert item["agent_name"] == agent["name"]
    assert item["answer"] == ANSWER
    assert item["reference_answer"] is None
    assert item["chunks"] == [
        {"label": "C1", "document_name": "leave.txt", "text": LEAVE, "cited": True}
    ]
    # The follow-up is shown with the turn its Version remembered, as the judge was given it.
    assert item["remembered_turns"] == [{"question": "How much annual leave?", "answer": ANSWER}]
    assert first[0]["remembered_turns"] == []
    assert (await agreement(owner))["current"]["reviews"] == 4
    assert (await agreement(owner))["current"]["agreed"] == 2


async def test_error_and_skipped_live_verdicts_are_never_served(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    held_back: list[uuid.UUID],
) -> None:
    calls = 0

    def outage_once(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")

    scripted(app, judgement=outage_once)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    await conversation(visitor, agent, "How much annual leave?")
    await conversation(visitor, agent, "And sick days?")
    errored, skipped = held_back
    await judge_now(errored)
    # The second reply's Conversation is deleted before it is judged: it is skipped.
    rows = (await listed(owner, agent["project_id"]))["items"]
    deleted = await owner.client.delete(
        conversations_path(owner, agent["project_id"], rows[0]["id"])
    )
    assert deleted.status_code == 204, deleted.text
    await judge_now(skipped)

    assert calls == 1
    assert (await next_item(owner))["item"] is None


async def test_only_the_current_evaluation_models_live_verdicts_are_served(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await remembering(app, owner, 0)
    await conversation(visitor, agent, "How much annual leave?")
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")

    changed = await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")

    assert changed.status_code == 200, changed.text
    # The Default Model judged the reply: nothing is left for the new Evaluation Model.
    assert (await next_item(owner))["item"] is None
    await set_evaluation_model(owner, None, None)
    assert len(await drained(owner)) == 2


async def test_a_live_check_has_one_review_and_reviewing_it_again_replaces_it(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await remembering(app, owner, 0)
    await conversation(visitor, agent, "How much annual leave?")
    item = (await next_item(owner))["item"]
    await reviewed_item(owner, item, "fail", "It never says a year.")

    replaced = await reviewed_item(editor, item, "pass")

    (only,) = await reviews_of(app, owner)
    assert (only.check, only.outcome, only.reason) == (item["check"], "pass", None)
    assert only.verdict_id is None
    assert str(only.live_verdict_id) == item["live_verdict_id"]
    assert replaced["outcome"] == "pass"
    # The other check of the same Live Verdict is still to review, and then nothing is.
    (other,) = await drained(owner)
    assert (other["live_verdict_id"], other["check"]) != (item["live_verdict_id"], item["check"])
    assert (await agreement(owner))["current"]["reviews"] == 2


async def test_a_live_review_names_one_target_and_a_live_check(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    tenant_factory: TenantFactory,
) -> None:
    agent = await remembering(app, owner, 0)
    await conversation(visitor, agent, "How much annual leave?")
    item = (await next_item(owner))["item"]
    other = await tenant_factory()

    reference = await review_item(owner, {**item, "check": "reference_answer"}, "pass")
    no_check = await review_item(owner, {**item, "check": None}, "pass")
    both = await review_item(owner, {**item, "verdict_id": str(uuid.uuid4())}, "pass")
    neither = await review_item(owner, {**item, "live_verdict_id": None}, "pass")
    unknown = await review_item(owner, {**item, "live_verdict_id": str(uuid.uuid4())}, "pass")
    elsewhere = await review_item(other, item, "pass")

    assert [r.status_code for r in (reference, no_check, both, neither)] == [422] * 4
    assert (unknown.status_code, elsewhere.status_code) == (404, 404)
    assert (await next_item(other))["item"] is None
    assert await reviews_of(app, owner) == []


# Retention


async def test_the_purge_clears_the_reason_on_live_reviews_and_keeps_their_outcomes(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await remembering(app, owner, 0)
    assert (await set_window(owner, 7)).status_code == 200
    await conversation(visitor, agent, "I am Ada; how much leave?")
    old = (await next_item(owner))["item"]
    await reviewed_item(owner, old, "fail", "Ada would disagree.")
    clock.advance(timedelta(days=1))
    (new_events,) = await conversation(visitor, agent, "How much annual leave?")
    new = (await next_item(owner))["item"]
    while new["live_verdict_id"] == old["live_verdict_id"]:
        new = (await next_item(owner))["item"]
    await reviewed_item(owner, new, "fail", "Kept: the reply is still here.")
    before = await agreement(owner)
    # A week and an hour after the first reply, only it is older than the window.
    clock.advance(timedelta(days=6, hours=1))
    await roll_up(clock.now())

    await purge(clock.now())

    purged, kept = await reviews_of(app, owner)
    assert (purged.outcome, purged.evaluation_model_outcome) == ("fail", old_outcome(old))
    assert (purged.reason, purged.purged_at) == (None, clock.now())
    assert (kept.reason, kept.purged_at) == ("Kept: the reply is still here.", None)
    assert await agreement(owner) == before
    # The first reply's other check left the sample with its text; the second's is still there.
    (left,) = await drained(owner)
    assert left["live_verdict_id"] == new["live_verdict_id"]
    assert new_events


def old_outcome(item: dict[str, Any]) -> str:
    return "pass" if (GROUNDED if item["check"] == "grounding" else ANSWERS)["passed"] else "fail"


async def test_deleting_a_conversation_clears_its_live_reviews_reasons_at_once(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await remembering(app, owner, 0)
    await conversation(visitor, agent, "I am Ada; how much leave?")
    item = (await next_item(owner))["item"]
    await reviewed_item(owner, item, "pass", "Ada's leave is right.")
    before = await agreement(owner)
    (row,) = (await listed(owner, agent["project_id"]))["items"]
    clock.advance(timedelta(minutes=5))

    deleted = await owner.client.delete(conversations_path(owner, agent["project_id"], row["id"]))

    assert deleted.status_code == 204, deleted.text
    (review,) = await reviews_of(app, owner)
    assert (review.outcome, review.reason, review.purged_at) == ("pass", None, clock.now())
    assert await agreement(owner) == before
    assert (await next_item(owner))["item"] is None


async def test_a_reply_whose_remembered_turn_is_purged_leaves_the_sample(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await remembering(app, owner, 1)
    assert (await set_window(owner, 7)).status_code == 200
    token = await conversation_token(visitor, agent["public_id"])
    # The follow-up comes a day later in the same Conversation.
    for question in ("How much annual leave?", "What about part-timers?"):
        response = await send(visitor, agent["public_id"], token, question)
        assert response.status_code == 200, response.text
        clock.advance(timedelta(days=1))
    clock.advance(timedelta(days=5, hours=1))
    await roll_up(clock.now())

    # The first turn is older than the window and Purged; the follow-up isn't, but the turn it
    # remembered is gone, so it can't be shown as it was judged.
    await purge(clock.now())

    assert (await next_item(owner))["item"] is None
