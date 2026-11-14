"""API seam: JSON bodies with non-finite numbers (AGT-F6). Python's JSON parser accepts the
``NaN``, ``Infinity`` and ``-Infinity`` literals, which strict JSON does not. Such a value is
refused with the usual 422 validation error, never a 500, and the error still says what the
rejected input was, spelled as the literal the client sent."""

import json
from typing import Any

import pytest

from tests.agents import FULL_DEFAULT_DRAFT, agents_path, create_agent
from tests.conftest import SignedUpMember
from tests.documents import create_project

NON_FINITE = ["NaN", "Infinity", "-Infinity"]


def _with_literal(body: dict[str, Any], marker: str, literal: str) -> str:
    """The body as JSON, with the string ``marker`` replaced by a bare ``literal``."""
    return json.dumps(body).replace(f'"{marker}"', literal)


@pytest.mark.parametrize("literal", NON_FINITE)
@pytest.mark.parametrize(
    ("group", "field"),
    [("behaviour", "temperature"), ("retrieval", "hybrid_weight"), ("retrieval", "min_score")],
)
async def test_a_non_finite_number_in_a_draft_is_refused_with_422(
    owner: SignedUpMember, group: str, field: str, literal: str
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = json.loads(json.dumps(FULL_DEFAULT_DRAFT))
    draft[group][field] = "__non_finite__"

    response = await owner.client.put(
        agents_path(owner, project_id, agent["id"], "draft"),
        content=_with_literal(draft, "__non_finite__", literal),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422, response.text
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", group, field]
    assert error["type"] == "finite_number"
    assert error["input"] == literal
    unchanged = await owner.client.get(agents_path(owner, project_id, agent["id"]))
    assert unchanged.json()["draft"] == FULL_DEFAULT_DRAFT


@pytest.mark.parametrize("literal", NON_FINITE)
async def test_a_non_finite_number_in_any_body_is_refused_with_422(
    owner: SignedUpMember, literal: str
) -> None:
    response = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/projects",
        content=_with_literal({"name": "__non_finite__"}, "__non_finite__", literal),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422, response.text
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", "name"]
    assert error["input"] == literal


async def test_non_finite_numbers_nested_in_the_rejected_input_are_spelled_out(
    owner: SignedUpMember,
) -> None:
    response = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/projects",
        content='{"name": {"low": -Infinity, "values": [NaN, 1.5, Infinity]}}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422, response.text
    (error,) = response.json()["detail"]
    assert error["input"] == {"low": "-Infinity", "values": ["NaN", 1.5, "Infinity"]}


async def test_ordinary_validation_errors_keep_their_shape(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = json.loads(json.dumps(FULL_DEFAULT_DRAFT))
    draft["behaviour"]["temperature"] = 1.5

    response = await owner.client.put(
        agents_path(owner, project_id, agent["id"], "draft"), json=draft
    )

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", "behaviour", "temperature"]
    assert error["type"] == "less_than_equal"
    assert error["input"] == 1.5
    assert error["ctx"] == {"le": 1.0}
