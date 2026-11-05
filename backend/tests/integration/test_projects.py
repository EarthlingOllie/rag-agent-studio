"""API seam: Editors create, rename, describe and Archive Projects; Owners restore them.

Everything is observed through the API: the Projects list, each Project, the answers of
Project routes, and Audit Events from the Audit list endpoint.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock

ARCHIVED = "This Project is archived. An Owner can restore it."


def projects_path(organisation_id: str, project_id: str | None = None) -> str:
    path = f"/api/organisations/{organisation_id}/projects"
    return path if project_id is None else f"{path}/{project_id}"


async def create_project(
    member: SignedUpMember, name: str = "HR handbook", description: str = ""
) -> dict[str, Any]:
    response = await member.client.post(
        projects_path(member.organisation_id), json={"name": name, "description": description}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def listed(member: SignedUpMember, **params: str) -> list[dict[str, Any]]:
    response = await member.client.get(projects_path(member.organisation_id), params=params)
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()
    return result


# Creating and listing


async def test_an_editor_creates_a_project_that_is_listed_with_its_counts(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    created = await create_project(editor, "HR handbook", "Policies for the HR Agent")

    assert created["name"] == "HR handbook"
    assert created["description"] == "Policies for the HR Agent"
    assert created["archived_at"] is None
    assert (created["document_count"], created["agent_count"]) == (0, 0)
    assert await listed(owner) == [created]


async def test_a_new_project_has_no_description_unless_given(owner: SignedUpMember) -> None:
    response = await owner.client.post(
        projects_path(owner.organisation_id), json={"name": "  Sales enablement  "}
    )

    assert response.status_code == 201, response.text
    assert (response.json()["name"], response.json()["description"]) == ("Sales enablement", "")


async def test_projects_are_listed_by_name(owner: SignedUpMember) -> None:
    for name in ("sales", "HR", "apple pie", "Product support"):
        await create_project(owner, name)

    # Upper and lower case sort together, whatever the database's collation.
    assert [p["name"] for p in await listed(owner)] == [
        "apple pie",
        "HR",
        "Product support",
        "sales",
    ]


async def test_the_list_shows_only_this_organisations_projects(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    ours = await create_project(owner, "Ours")
    await create_project(other, "Theirs")

    assert await listed(owner) == [ours]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 201},
        {"name": "Fine", "description": "x" * 2001},
    ],
    ids=["no name", "empty name", "blank name", "long name", "long description"],
)
async def test_a_project_needs_a_name_and_bounded_text(
    owner: SignedUpMember, body: dict[str, Any]
) -> None:
    response = await owner.client.post(projects_path(owner.organisation_id), json=body)

    assert response.status_code == 422
    assert await listed(owner) == []


async def test_a_project_is_read_by_its_id(owner: SignedUpMember) -> None:
    created = await create_project(owner, "HR handbook", "Policies")

    response = await owner.client.get(projects_path(owner.organisation_id, created["id"]))

    assert (response.status_code, response.json()) == (200, created)


async def test_an_unknown_project_is_not_found(owner: SignedUpMember) -> None:
    path = projects_path(owner.organisation_id, str(uuid.uuid4()))

    answers = [
        await owner.client.get(path),
        await owner.client.patch(path, json={"name": "New"}),
        await owner.client.post(f"{path}/archive"),
        await owner.client.post(f"{path}/restore"),
    ]

    assert [(a.status_code, a.json()) for a in answers] == [(404, {"detail": "Not found"})] * 4


# Renaming and describing


async def update(member: SignedUpMember, project_id: str, **fields: str) -> httpx.Response:
    return await member.client.patch(projects_path(member.organisation_id, project_id), json=fields)


async def test_an_editor_renames_a_project_and_edits_its_description(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project = await create_project(owner, "HR", "Old description")

    renamed = await update(editor, project["id"], name="People team")
    described = await update(editor, project["id"], description="  Policies and benefits  ")

    assert renamed.status_code == described.status_code == 200
    assert renamed.json()["name"] == "People team"
    assert renamed.json()["description"] == "Old description"
    assert (described.json()["name"], described.json()["description"]) == (
        "People team",
        "Policies and benefits",
    )
    assert [(p["name"], p["description"]) for p in await listed(owner)] == [
        ("People team", "Policies and benefits")
    ]


async def test_a_project_cannot_be_renamed_to_nothing(owner: SignedUpMember) -> None:
    project = await create_project(owner, "HR")

    response = await update(owner, project["id"], name=" ")

    assert response.status_code == 422
    assert [p["name"] for p in await listed(owner)] == ["HR"]


# Archiving and restoring


async def archive(member: SignedUpMember, project_id: str) -> httpx.Response:
    return await member.client.post(f"{projects_path(member.organisation_id, project_id)}/archive")


async def restore(member: SignedUpMember, project_id: str) -> httpx.Response:
    return await member.client.post(f"{projects_path(member.organisation_id, project_id)}/restore")


async def test_archiving_hides_a_project_from_the_main_list(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    kept = await create_project(owner, "Kept")
    retired = await create_project(owner, "Retired")

    response = await archive(editor, retired["id"])

    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["archived_at"]) == clock.now()
    assert await listed(owner) == [kept]
    assert [p["id"] for p in await listed(owner, archived="true")] == [retired["id"]]
    # The archived Project can still be opened, so it can be restored.
    opened = await owner.client.get(projects_path(owner.organisation_id, retired["id"]))
    assert opened.json() == response.json()


async def test_an_archived_project_stops_serving_changes_until_restored(
    owner: SignedUpMember,
) -> None:
    project = await create_project(owner, "HR")
    await archive(owner, project["id"])

    renamed = await update(owner, project["id"], name="People")
    archived_again = await archive(owner, project["id"])

    assert (renamed.status_code, renamed.json()) == (409, {"detail": ARCHIVED})
    assert (archived_again.status_code, archived_again.json()) == (409, {"detail": ARCHIVED})
    assert [p["name"] for p in await listed(owner, archived="true")] == ["HR"]


async def test_owners_restore_an_archived_project(owner: SignedUpMember) -> None:
    project = await create_project(owner, "HR")
    await archive(owner, project["id"])

    response = await restore(owner, project["id"])

    assert response.status_code == 200, response.text
    assert response.json() == project
    assert await listed(owner) == [project]
    assert await listed(owner, archived="true") == []
    assert (await update(owner, project["id"], name="People")).status_code == 200


async def test_editors_cannot_restore_a_project(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project = await create_project(owner, "HR")
    await archive(editor, project["id"])

    response = await restore(editor, project["id"])

    assert (response.status_code, response.json()) == (403, {"detail": "Only Owners can do this"})
    assert await listed(owner) == []


async def test_only_an_archived_project_can_be_restored(owner: SignedUpMember) -> None:
    project = await create_project(owner, "HR")

    response = await restore(owner, project["id"])

    assert (response.status_code, response.json()) == (
        409,
        {"detail": "This Project isn't archived."},
    )


# Audit Events


async def audit_events(owner: SignedUpMember, action: str) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events", params={"action": action}
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_create_archive_and_restore_are_audit_events(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    clock.advance(timedelta(minutes=1))
    project = await create_project(editor, "HR handbook", "Policies")
    clock.advance(timedelta(minutes=1))
    await archive(editor, project["id"])
    clock.advance(timedelta(minutes=1))
    await restore(owner, project["id"])

    (created,) = await audit_events(owner, "project.created")
    (archived,) = await audit_events(owner, "project.archived")
    (restored,) = await audit_events(owner, "project.restored")

    target = {"type": "project", "id": project["id"]}
    assert (created["actor"]["id"], created["target"]) == (editor.member_id, target)
    assert (created["before"], created["after"]) == (
        None,
        {"name": "HR handbook", "description": "Policies"},
    )
    assert (archived["actor"]["id"], archived["target"]) == (editor.member_id, target)
    assert (archived["before"], archived["after"]) == (
        {"name": "HR handbook", "archived": False},
        {"name": "HR handbook", "archived": True},
    )
    assert (restored["actor"]["id"], restored["target"]) == (owner.member_id, target)
    assert (restored["before"], restored["after"]) == (
        {"name": "HR handbook", "archived": True},
        {"name": "HR handbook", "archived": False},
    )
    times = [datetime.fromisoformat(e["occurred_at"]) for e in (created, archived, restored)]
    assert times == [datetime(2026, 11, 5, 9, minute, tzinfo=UTC) for minute in (1, 2, 3)]


async def test_refused_changes_record_no_audit_event(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project = await create_project(owner, "HR")
    await restore(owner, project["id"])  # not archived
    await archive(owner, project["id"])
    await archive(owner, project["id"])  # already archived
    await restore(editor, project["id"])  # not an Owner

    assert len(await audit_events(owner, "project.archived")) == 1
    assert await audit_events(owner, "project.restored") == []
