"""API seam: out-of-range query values are refused with 422, never a 500.

A page number or offset so large that the SQL OFFSET overflows a 64-bit integer, and a UTC day
so close to the ends of the calendar that a day either side of it does not exist, are both
input errors. Assertions are on HTTP responses only."""

from typing import Any

import pytest
from fastapi import FastAPI

from tests.conftest import SignedUpMember
from tests.documents import create_project, project_path, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_audit_events import _events_path
from tests.integration.test_conversations import conversations_path
from tests.integration.test_playground import LEAVE
from tests.integration.test_time_series import get_series
from tests.integration.test_version_metrics import get_metrics, live_agent

INT64_MAX = 2**63 - 1


async def test_a_conversations_page_past_the_last_possible_one_is_refused(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)

    response = await owner.client.get(
        conversations_path(owner, project_id), params={"page": INT64_MAX}
    )

    assert response.status_code == 422, response.text


async def test_an_audit_events_page_past_the_last_possible_one_is_refused(
    owner: SignedUpMember,
) -> None:
    response = await owner.client.get(
        _events_path(owner.organisation_id), params={"page": INT64_MAX}
    )

    assert response.status_code == 422, response.text


async def test_the_largest_allowed_pages_are_still_answered(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)

    conversations = await owner.client.get(
        conversations_path(owner, project_id), params={"page": 1_000_000}
    )
    events = await owner.client.get(_events_path(owner.organisation_id), params={"page": 1_000_000})

    assert conversations.status_code == 200, conversations.text
    assert conversations.json()["items"] == []
    assert events.status_code == 200, events.text
    assert events.json()["items"] == []


@pytest.mark.parametrize("offset", [2**63, INT64_MAX, 10**9 + 1])
async def test_a_chunk_offset_past_the_last_possible_one_is_refused(
    app: FastAPI, owner: SignedUpMember, offset: int
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "leave.txt", LEAVE.encode())

    response = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{document['id']}/chunks",
        params={"offset": offset},
    )

    assert response.status_code == 422, response.text


async def test_the_largest_allowed_chunk_offset_is_still_answered(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "leave.txt", LEAVE.encode())

    response = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{document['id']}/chunks",
        params={"offset": 10**9},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"granularity": "month", "start": "9999-01-01", "end": "9999-12-31"},
        {"granularity": "day", "start": "9999-12-31", "end": "9999-12-31"},
        {"end": "0001-01-02"},
        {"start": "0001-01-01", "end": "0001-01-07", "granularity": "week"},
        {"start": "1999-12-31", "end": "2000-01-05"},
        {"start": "2027-11-07", "end": "2027-11-07"},
    ],
)
async def test_a_time_series_with_days_outside_the_sane_window_is_refused(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, params: dict[str, str]
) -> None:
    agent = await live_agent(app, owner)

    response = await get_series(owner, agent, metric="conversations", **params)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "params", [{"end": "0001-01-02"}, {"start": "9999-12-31", "end": "9999-12-31"}]
)
async def test_version_metrics_with_days_outside_the_sane_window_are_refused(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, params: dict[str, str]
) -> None:
    agent = await live_agent(app, owner)

    response = await get_metrics(owner, agent, **params)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2000-01-01", "end": "2000-01-31"},
        {"start": "2027-11-01", "end": "2027-11-06"},
    ],
)
async def test_a_time_series_at_the_edges_of_the_sane_window_is_answered(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, params: dict[str, Any]
) -> None:
    agent = await live_agent(app, owner)

    response = await get_series(owner, agent, metric="conversations", **params)

    assert response.status_code == 200, response.text
    assert (response.json()["start"], response.json()["end"]) == (params["start"], params["end"])
