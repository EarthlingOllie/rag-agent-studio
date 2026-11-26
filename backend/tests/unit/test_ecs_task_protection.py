"""The production Scale-in protection adapter (spec 22): it calls the ECS agent's task-protection
endpoint, with an expiry, and clears the task's protection only when no other job in the task
holds it. The agent is played by an ``httpx.MockTransport`` that records each request."""

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.settings import load_settings
from app.jobs.protection import (
    EcsTaskProtection,
    NoProtection,
    ProtectionRefusedError,
    build_protection,
)

AGENT_URI = "http://169.254.170.2/api/0f1e2d3c-task"
STATE_URL = f"{AGENT_URI}/task-protection/v1/state"
FIRST, SECOND = uuid.uuid4(), uuid.uuid4()


class Agent:
    """The ECS agent's endpoint: records each request and answers with ``answer``."""

    def __init__(self, status: int = 200, answer: dict[str, Any] | None = None) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self._status = status
        self._answer = answer if answer is not None else {"protection": {"ProtectionEnabled": True}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, str(request.url), json.loads(request.content)))
        return httpx.Response(self._status, json=self._answer)

    def bodies(self) -> list[dict[str, Any]]:
        return [body for _, _, body in self.requests]


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def adapter(agent: Agent, holders: Path, clock: Clock | None = None) -> EcsTaskProtection:
    return EcsTaskProtection(
        AGENT_URI + "/",
        5,
        holders,
        transport=httpx.MockTransport(agent),
        now=clock or Clock(),
    )


async def test_protect_and_renew_set_protection_with_an_expiry_a_few_minutes_ahead(
    tmp_path: Path,
) -> None:
    agent = Agent()
    protection = adapter(agent, tmp_path / "holders")

    await protection.protect(FIRST)
    await protection.renew(FIRST)

    enabled = {"ProtectionEnabled": True, "ExpiresInMinutes": 5}
    assert agent.requests == [("PUT", STATE_URL, enabled), ("PUT", STATE_URL, enabled)]


async def test_release_clears_protection_when_no_other_job_holds_it(tmp_path: Path) -> None:
    agent = Agent()
    protection = adapter(agent, tmp_path / "holders")
    await protection.protect(FIRST)

    await protection.release(FIRST)

    assert agent.bodies()[-1] == {"ProtectionEnabled": False}


async def test_release_keeps_protection_while_another_job_in_the_task_holds_it(
    tmp_path: Path,
) -> None:
    """Two worker processes share the task: the first job to end leaves the second protected."""
    agent = Agent()
    first, second = adapter(agent, tmp_path), adapter(agent, tmp_path)
    await first.protect(FIRST)
    await second.protect(SECOND)

    await first.release(FIRST)
    assert agent.bodies()[-1] == {"ProtectionEnabled": True, "ExpiresInMinutes": 5}

    await second.release(SECOND)
    assert agent.bodies()[-1] == {"ProtectionEnabled": False}


async def test_a_holder_older_than_the_expiry_belongs_to_a_dead_process_and_is_ignored(
    tmp_path: Path,
) -> None:
    agent = Agent()
    clock = Clock()
    protection = adapter(agent, tmp_path, clock)
    await protection.protect(SECOND)  # Its process dies and never releases.
    clock.now += 5 * 60 + 1
    await protection.protect(FIRST)

    await protection.release(FIRST)

    assert agent.bodies()[-1] == {"ProtectionEnabled": False}


async def test_releasing_before_anything_was_protected_clears_protection(tmp_path: Path) -> None:
    agent = Agent()

    await adapter(agent, tmp_path / "never-made").release(FIRST)

    assert agent.bodies() == [{"ProtectionEnabled": False}]


@pytest.mark.parametrize(
    ("status", "answer"),
    [
        (200, {"failure": {"Reason": "AccessDeniedException"}}),
        (500, {"error": {"Code": "ServerException"}}),
        (400, {}),
    ],
)
async def test_an_agent_that_does_not_set_protection_raises(
    tmp_path: Path, status: int, answer: dict[str, Any]
) -> None:
    protection = adapter(Agent(status, answer), tmp_path)

    with pytest.raises(ProtectionRefusedError):
        await protection.protect(FIRST)


async def test_an_empty_error_answer_raises(tmp_path: Path) -> None:
    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    protection = EcsTaskProtection(AGENT_URI, 5, tmp_path, transport=httpx.MockTransport(empty))

    with pytest.raises(ProtectionRefusedError):
        await protection.release(FIRST)


async def test_no_protection_does_nothing_and_never_fails() -> None:
    protection = NoProtection()

    await protection.protect(FIRST)
    await protection.renew(FIRST)
    await protection.release(FIRST)


def test_ecs_protection_is_used_where_the_ecs_agent_is(
    settings_env: pytest.MonkeyPatch,
) -> None:
    assert isinstance(build_protection(load_settings()), NoProtection)

    settings_env.setenv("ECS_AGENT_URI", AGENT_URI)
    built = build_protection(load_settings())

    assert isinstance(built, EcsTaskProtection)
    assert built._url == STATE_URL
    assert built._expires_in_minutes == 5


def test_the_expiry_is_a_setting(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("ECS_AGENT_URI", AGENT_URI)
    settings_env.setenv("SCALE_IN_PROTECTION_MINUTES", "10")

    built = build_protection(load_settings())

    assert isinstance(built, EcsTaskProtection)
    assert built._expires_in_minutes == 10
