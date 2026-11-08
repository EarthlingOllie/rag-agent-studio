"""The demo Organisation's history (ticket 10-02): four weeks of Versions and Visitor
Conversations, so Live History, the Instructions rollout and the comparison charts have a story.

A fresh seed runs under a ``ShiftedClock`` that starts four weeks ago, so everything the
platform stamps with the Clock port (Audit Events, Versions, Live History, feedback and
ratings) happened then. The story (``content``) is played day by day through the API: the
Editor and Owner publish, revert and roll out Instructions; Visitors open the widget, ask the
Agents questions through the real runtime (answered by the demo provider's ``FunctionModel``),
give thumbs and rate Conversations, with choices drawn from a fixed random seed and each
Version's ``Reception``. What the database stamps itself (Conversations and Messages, and the
foundation's rows) is backfilled to the clock's time, the only direct writes. Finally the usage
rollup runs for every historical day, as Beat would have.
"""

import asyncio
import json
import random
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.analytics.rollup import roll_up
from app.conversations.models import Conversation, Message
from app.credentials.models import ProviderCredential
from app.documents.models import Document, DocumentStatus
from app.feedback.models import ConversationRating, ConversationRatingChange, MessageFeedback
from app.projects.models import Project
from app.seed import content
from app.seed.client import SeedApi, SeedError, new_client
from app.tags.models import Tag
from app.tenancy.models import Organisation

# Visitors chat between these hours (UTC); releases happen before them.
OPENING, CLOSING = time(9), time(18)
RELEASE_TIME = time(7, 30)
_BOOT = re.compile(r'<script id="widget-boot" type="application/json">(.*?)</script>', re.DOTALL)
_DONE = re.compile(r"event: done\ndata: (.*)\n")


class ShiftedClock:
    """The Clock port, set in the past: time runs at its usual pace from wherever it was last
    sent, and it is only ever sent forward."""

    def __init__(self, at: datetime) -> None:
        self._offset = datetime.now(UTC) - at

    def now(self) -> datetime:
        return datetime.now(UTC) - self._offset

    def travel_to(self, at: datetime) -> None:
        """Moves the clock on to ``at``; a time it has already passed leaves it where it is."""
        self._offset = min(self._offset, datetime.now(UTC) - at)


def history_start(now: datetime) -> datetime:
    """When the demo Organisation was set up: early on the first day of its history."""
    return _at(now.astimezone(UTC).date() - timedelta(days=content.HISTORY_DAYS), time(6))


def _at(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=UTC)


async def wait_for_documents(
    api: SeedApi,
    project: str,
    *,
    attempts: int = 300,
    interval: float = 2.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Waits until ingestion has made every Document ready (in ``docker compose`` the worker
    does it), so Visitors' questions find Chunks."""
    for _ in range(attempts):
        statuses = {
            d["status"] for d in await api.call("GET", api.path("projects", project, "documents"))
        }
        if DocumentStatus.FAILED in statuses:
            raise SeedError("A demo Document failed ingestion; see the worker's log.")
        if statuses <= {DocumentStatus.READY}:
            return
        await sleep(interval)
    raise SeedError("The demo Documents weren't ready in time. Is the worker running?")


@dataclass
class _Story:
    app: FastAPI
    clock: ShiftedClock
    owner: SeedApi
    editor: SeedApi
    project: str
    agents: dict[str, Any]
    rng: random.Random
    history: content.History
    # Each Agent's Live Version number, as the story moves it.
    live: dict[str, int]

    def agent_path(self, name: str, *rest: str) -> str:
        return self.owner.path("projects", self.project, "agents", self.agents[name]["id"], *rest)

    async def publish_hr(self, api: SeedApi, release: content.Release) -> None:
        path = self.agent_path(content.HR_AGENT)
        agent = await api.call("GET", path)
        draft = agent["draft"]
        await api.call(
            "PUT",
            f"{path}/draft",
            body={
                **draft,
                "behaviour": {**draft["behaviour"], "system_prompt": release.system_prompt},
                "retrieval": {
                    **draft["retrieval"],
                    "top_k": release.top_k,
                    "citations": release.citations,
                },
            },
        )
        published = await api.call(
            "POST", f"{path}/versions", expect=201, body={"note": release.note}
        )
        self.live[content.HR_AGENT] = published["number"]

    async def release(self, day: int) -> None:
        """What happens to the Agents on ``day`` (days before today), before Visitors arrive."""
        if day == content.HISTORY_DAYS:
            await self.publish_hr(self.owner, content.HR_V1)
        elif day == 17:
            await self.publish_hr(self.editor, content.HR_V2)
        elif day == 10:
            reverted = await self.owner.call("POST", self.agent_path(content.HR_AGENT, "revert"))
            self.live[content.HR_AGENT] = reverted["number"]
        elif day == 6:
            await self._instructions_v2()
        elif day == 3:
            await self.publish_hr(self.editor, content.HR_V3)

    async def _instructions_v2(self) -> None:
        path = self.owner.path("projects", self.project, "instructions")
        await self.owner.call("PUT", path, body={"markdown": content.INSTRUCTIONS_V2})
        version = await self.owner.call(
            "POST", f"{path}/versions", expect=201, body={"note": content.INSTRUCTIONS_V2_NOTE}
        )
        # Rolled out to the Low-budget helper; the Product FAQ is left behind on v1.
        await self.owner.call(
            "POST",
            self.owner.path("projects", self.project, "agents", "bulk-publish"),
            body={
                "agent_ids": [self.agents[content.BUDGET_AGENT]["id"]],
                "instructions_version_id": version["id"],
                "note": content.BULK_NOTE,
            },
        )

    def visits(self, day: date) -> list[tuple[datetime, str]]:
        """When each Visitor opens which Agent's widget on ``day``."""
        length = (_at(day, CLOSING) - _at(day, OPENING)).total_seconds()
        found = [
            (_at(day, OPENING) + timedelta(seconds=self.rng.uniform(0, length)), name)
            for name, count in sorted(self.history.conversations_per_day.items())
            for _ in range(count)
        ]
        return sorted(found)

    async def visit(self, name: str) -> None:
        """One Visitor Conversation, as the widget has it."""
        public_id = self.agents[name]["public_id"]
        reception = content.RECEPTION[(name, self.live[name])]
        async with new_client(self.app) as browser:
            visitor = SeedApi(browser)
            shell = await browser.get(f"/widget/a/{public_id}")
            boot = json.loads(_BOOT.findall(shell.text)[0])
            widget = f"/api/widget/agents/{public_id}"
            started = await visitor.call(
                "POST",
                f"{widget}/conversations",
                expect=201,
                body={"bootstrap_token": boot["bootstrap_token"]},
            )
            bearer = {"Authorization": f"Bearer {started['conversation_token']}"}
            times: list[datetime] = []
            replies: list[str] = []
            turns = self.rng.choices(
                list(content.TURN_WEIGHTS), list(content.TURN_WEIGHTS.values())
            )
            for turn in range(turns[0]):
                if turn:
                    self.clock.travel_to(
                        self.clock.now() + timedelta(seconds=self.rng.uniform(30, 150))
                    )
                question = self.rng.choice(content.QUESTIONS[name])
                times.append(self.clock.now())
                answered = await browser.post(
                    f"{widget}/messages", json={"content": question}, headers=bearer
                )
                done = _DONE.search(answered.text)
                if done is None:
                    raise SeedError(f"{name} gave a Visitor no reply: {answered.text}")
                times.append(self.clock.now())
                reply = json.loads(done.group(1))["message_id"]
                replies.append(reply)
                if self.rng.random() < reception.vote:
                    thumb = "up" if self.rng.random() < reception.thumbs_up else "down"
                    await visitor.call(
                        "PUT",
                        f"{widget}/messages/{reply}/feedback",
                        body={"rating": thumb},
                        headers=bearer,
                    )
            if self.rng.random() < reception.rate:
                (score,) = self.rng.choices(range(1, 6), reception.scores)
                await visitor.call(
                    "PUT", f"{widget}/conversation/rating", body={"score": score}, headers=bearer
                )
        await _backfill_conversation(self.app, uuid.UUID(replies[0]), times)


async def _backfill_conversation(app: FastAPI, reply_id: uuid.UUID, times: list[datetime]) -> None:
    """Stamps the Conversation and its Messages with the clock's times instead of the
    database's, and its feedback and rating rows with the times the Clock port gave them."""
    async with app.state.sessionmaker() as session, session.begin():
        conversation_id = await session.scalar(
            select(Message.conversation_id).where(Message.id == reply_id)
        )
        message_ids = list(
            await session.scalars(
                select(Message.id)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.seq)
            )
        )
        for message_id, at in zip(message_ids, times, strict=False):
            await session.execute(
                update(Message).where(Message.id == message_id).values(created_at=at)
            )
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(created_at=times[0], last_activity_at=times[-1])
        )
        await session.execute(
            update(MessageFeedback)
            .where(MessageFeedback.message_id.in_(message_ids))
            .values(created_at=MessageFeedback.updated_at)
        )
        await session.execute(
            update(ConversationRating)
            .where(ConversationRating.conversation_id == conversation_id)
            .values(created_at=ConversationRating.rated_at)
        )
        await session.execute(
            update(ConversationRatingChange)
            .where(ConversationRatingChange.conversation_id == conversation_id)
            .values(created_at=ConversationRatingChange.changed_at)
        )


async def _backfill_foundation(
    session: AsyncSession, organisation_id: uuid.UUID, start: datetime
) -> None:
    """Stamps what the Organisation was set up with as made when its history starts."""
    await session.execute(
        update(Organisation).where(Organisation.id == organisation_id).values(created_at=start)
    )
    for model in (Project, Document, Tag, Agent, ProviderCredential):
        await session.execute(
            update(model)
            .where(model.organisation_id == organisation_id, model.created_at > start)
            .values(created_at=start)
        )


async def generate(
    app: FastAPI,
    owner: SeedApi,
    clock: ShiftedClock,
    start: datetime,
    project: str,
    agents: dict[str, Any],
    history: content.History,
) -> None:
    """Plays the story from its first day to yesterday, rolls usage up for every day, and
    backfills the foundation's timestamps to ``start``."""
    today = (start + timedelta(days=content.HISTORY_DAYS)).date()
    await wait_for_documents(owner, project)
    async with new_client(app) as client:
        editor = SeedApi(client)
        await editor.call(
            "POST",
            "/api/auth/sign-in",
            body={"email": content.EDITOR.email, "password": content.EDITOR.password},
        )
        editor.organisation = owner.organisation
        story = _Story(
            app,
            clock,
            owner,
            editor,
            project,
            agents,
            random.Random(history.random_seed),  # noqa: S311 (a fixed seed, for repeatable demo data)
            history,
            {content.SHOP_AGENT: 1},
        )
        for day in range(content.HISTORY_DAYS, 0, -1):
            on = today - timedelta(days=day)
            clock.travel_to(_at(on, RELEASE_TIME))
            await story.release(day)
            for at, name in story.visits(on):
                clock.travel_to(at)
                await story.visit(name)
    for day in range(content.HISTORY_DAYS, 0, -1):
        # Just after midnight, as Beat's hourly run would: it finalises the day before.
        await roll_up(app.state.sessionmaker, _at(today - timedelta(days=day - 1), time(0, 5)))
    async with app.state.sessionmaker() as session, session.begin():
        await _backfill_foundation(session, uuid.UUID(owner.organisation), start)
