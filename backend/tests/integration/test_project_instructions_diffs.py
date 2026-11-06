"""API seam: diffs of Project Instructions. An Editor compares any two Instructions Versions,
or the Draft with the Current Version, as a line diff of their markdown."""

import uuid
from typing import Any

import httpx

from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_project_instructions_versions import (
    instructions_path,
    published,
    revert,
    save_draft,
)


async def diff(member: SignedUpMember, project_id: str, source: str, target: str) -> httpx.Response:
    return await member.client.get(
        f"{instructions_path(member, project_id)}/diff", params={"from": source, "to": target}
    )


async def diffed(member: SignedUpMember, project_id: str, source: str, target: str) -> Any:
    response = await diff(member, project_id, source, target)
    assert response.status_code == 200, response.text
    return response.json()


def number(version: dict[str, Any]) -> dict[str, Any]:
    return {"id": version["id"], "number": version["number"]}


async def test_two_instructions_versions_compared_line_by_line(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    v1 = await published(owner, project_id, "# Rules\nBe kind.\nCite sources.", "v1")
    v2 = await published(owner, project_id, "# Rules\nBe kind.\nAlways cite sources.", "v2")

    body = await diffed(editor, project_id, v1["id"], v2["id"])

    assert body == {
        "from": {"kind": "version", "version": number(v1)},
        "to": {"kind": "version", "version": number(v2)},
        "lines": [
            {"op": "equal", "text": "# Rules"},
            {"op": "equal", "text": "Be kind."},
            {"op": "delete", "text": "Cite sources."},
            {"op": "insert", "text": "Always cite sources."},
        ],
    }


async def test_the_draft_compared_with_the_current_version(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    v1 = await published(owner, project_id, "Be kind.", "v1")
    v2 = await published(owner, project_id, "Be very kind.", "v2")
    assert (await revert(owner, project_id)).status_code == 200
    await save_draft(owner, project_id, "Be kind.\nBe brief.")

    body = await diffed(owner, project_id, "current", "draft")

    # Current is v1 again after the revert, not the newest Version.
    assert body["from"] == {"kind": "version", "version": number(v1)}
    assert body["to"] == {"kind": "draft", "version": None}
    assert body["lines"] == [
        {"op": "equal", "text": "Be kind."},
        {"op": "insert", "text": "Be brief."},
    ]
    assert v2["number"] == 2


async def test_instructions_that_were_never_published_have_no_current_version(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    await save_draft(owner, project_id, "Be kind.")

    response = await diff(owner, project_id, "current", "draft")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        "The Instructions have never been published, so there's no Current Version."
    )
    assert (await diffed(owner, project_id, "draft", "draft"))["lines"] == [
        {"op": "equal", "text": "Be kind."}
    ]


async def test_a_version_of_another_project_or_organisation_is_not_found(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    other_project = await create_project(owner, "Other")
    theirs = await published(owner, other_project, "Theirs", "v1")
    mine = await published(owner, project_id, "Mine", "v1")
    stranger = await tenant_factory()

    for source in (theirs["id"], str(uuid.uuid4())):
        assert (await diff(owner, project_id, source, "draft")).status_code == 404
    outside = await stranger.client.get(
        f"{instructions_path(owner, project_id)}/diff", params={"from": mine["id"], "to": "draft"}
    )
    assert outside.status_code == 404
    assert (await diff(owner, project_id, "latest", "draft")).status_code == 422
