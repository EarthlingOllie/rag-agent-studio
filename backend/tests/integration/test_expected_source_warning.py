"""API seam: the Expected source warning, and Expected sources kept honest as Documents change.

A read on a Document names the Agents, and how many of their cases, holding an Expected source in
it, for the Studio to warn before the Document is deleted or a new Edition uploaded. When a new
Edition is swapped in its Expected sources are matched again at once, and deleting the Document
marks them Stale expectations straight away, without waiting for a Run.
"""

import uuid
from typing import Any

from fastapi import FastAPI

from tests.agents import create_automatic_agent
from tests.conftest import SignedUpMember, TenantFactory
from tests.documents import create_project, project_path, replace, upload
from tests.integration.test_evaluation import evaluation_path
from tests.integration.test_evaluation_expectations import (
    PARKING,
    add_case,
    leave_document,
    source,
)
from tests.integration.test_playground import ready_agent


def dependents_path(member: SignedUpMember, project_id: str, document_id: str) -> str:
    return f"{project_path(member, project_id)}/documents/{document_id}/expected-sources"


async def dependents(member: SignedUpMember, project_id: str, document_id: str) -> Any:
    response = await member.client.get(dependents_path(member, project_id, document_id))
    assert response.status_code == 200, response.text
    return response.json()


async def expected_sources(member: SignedUpMember, project_id: str, agent_id: str) -> list[Any]:
    """Each case's Expected sources as (document_id, document_name, passage, stale, reason)."""
    response = await member.client.get(evaluation_path(member, project_id, agent_id, "cases"))
    assert response.status_code == 200, response.text
    return [
        (s["document_id"], s["document_name"], s["passage"], s["stale"], s["stale_reason"])
        for case in response.json()
        for s in case["expected_sources"]
    ]


async def test_a_document_read_names_the_agents_and_case_counts_holding_its_expected_sources(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, helper_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    parking = await upload(app, owner, project_id, "parking.txt", PARKING.encode())
    assert await dependents(owner, project_id, leave["id"]) == {"agents": [], "passages": []}
    concierge = await create_automatic_agent(owner, project_id, "Concierge")
    # Two sources in one case count it once; a case on another Document isn't counted.
    await add_case(
        owner,
        project_id,
        helper_id,
        expected_sources=[source(leave["id"], "25 days"), source(leave["id"], "annual leave")],
    )
    await add_case(owner, project_id, helper_id, expected_sources=[source(leave["id"], "25 days")])
    await add_case(
        owner, project_id, helper_id, expected_sources=[source(parking["id"], "north car park")]
    )
    await add_case(
        owner, project_id, concierge["id"], expected_sources=[source(leave["id"], "a year")]
    )

    found = await dependents(owner, project_id, leave["id"])

    # By Agent name, and every distinct passage for the Document viewer to mark.
    assert found == {
        "agents": [
            {"agent_id": concierge["id"], "name": "Concierge", "case_count": 1},
            {"agent_id": helper_id, "name": "HR helper", "case_count": 2},
        ],
        "passages": ["25 days", "a year", "annual leave"],
    }
    assert await dependents(owner, project_id, parking["id"]) == {
        "agents": [{"agent_id": helper_id, "name": "HR helper", "case_count": 1}],
        "passages": ["north car park"],
    }


async def test_the_read_is_only_for_documents_of_the_members_project(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    _, project_id, _ = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    other_project = await create_project(owner, "Elsewhere")
    stranger = await tenant_factory()

    for member, project, document_id in (
        (owner, project_id, str(uuid.uuid4())),
        (owner, other_project, leave["id"]),
        (stranger, project_id, leave["id"]),
    ):
        response = await member.client.get(dependents_path(member, project, document_id))
        assert response.status_code == 404, response.text


async def test_a_new_edition_checks_its_expected_sources_again_at_once(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    parking = await upload(app, owner, project_id, "parking.txt", PARKING.encode())
    await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[
            source(leave["id"], "25 days"),
            source(leave["id"], "annual leave"),
            source(leave["id"], "30 days"),
            source(parking["id"], "north car park"),
        ],
    )
    before = await expected_sources(owner, project_id, agent_id)
    assert [stale for *_, stale, _ in before] == [False, False, True, False]

    replaced = await replace(
        app,
        owner,
        project_id,
        leave["id"],
        "leave-2027.txt",
        b"Everyone gets 25 days a year, rising to 30 days after five years.",
    )
    assert replaced.status_code == 202, replaced.text

    # The surviving passage stays valid, the missing one is stale and the returning one cleared;
    # another Document's Expected sources are untouched.
    assert await expected_sources(owner, project_id, agent_id) == [
        (leave["id"], "leave.txt", "25 days", False, None),
        (leave["id"], "leave.txt", "annual leave", True, "passage_missing"),
        (leave["id"], "leave.txt", "30 days", False, None),
        (parking["id"], "parking.txt", "north car park", False, None),
    ]


async def test_deleting_a_document_marks_its_expected_sources_stale_at_once(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    parking = await upload(app, owner, project_id, "parking.txt", PARKING.encode())
    await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[source(leave["id"], "25 days"), source(parking["id"], "north car park")],
    )

    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{parking['id']}"
    )

    assert deleted.status_code == 204, deleted.text
    # No Run needed: the Document's name stays for display.
    assert await expected_sources(owner, project_id, agent_id) == [
        (leave["id"], "leave.txt", "25 days", False, None),
        (None, "parking.txt", "north car park", True, "document_deleted"),
    ]
