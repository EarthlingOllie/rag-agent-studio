"""API seam: Project Instructions Versions. An Editor publishes the Instructions Draft with a
note as a new immutable, numbered Version that becomes the Current Version, lists the history,
and reverts the Current Version. Everything is observed through the API, including the Audit
Events."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.tenancy.erasure import erase_organisation
from tests.conftest import BACKEND_ROOT, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path
from tests.integration.test_project_deletion import delete_permanently
from tests.integration.test_projects import archive
from tests.integration.test_provider_credentials import audit_events

NOTHING_TO_PUBLISH = "The Draft is the same as the Current Version, so there's nothing to publish."
NOTHING_TO_REVERT = "There's no earlier Version to revert to."


def instructions_path(member: SignedUpMember, project_id: str) -> str:
    return f"{project_path(member, project_id)}/instructions"


async def save_draft(member: SignedUpMember, project_id: str, markdown: str) -> None:
    response = await member.client.put(
        instructions_path(member, project_id), json={"markdown": markdown}
    )
    assert response.status_code == 200, response.text


async def publish(member: SignedUpMember, project_id: str, note: str) -> httpx.Response:
    return await member.client.post(
        f"{instructions_path(member, project_id)}/versions", json={"note": note}
    )


async def revert(member: SignedUpMember, project_id: str) -> httpx.Response:
    return await member.client.post(f"{instructions_path(member, project_id)}/revert")


async def draft(member: SignedUpMember, project_id: str) -> str:
    response = await member.client.get(instructions_path(member, project_id))
    assert response.status_code == 200, response.text
    markdown: str = response.json()["markdown"]
    return markdown


async def history(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    response = await member.client.get(f"{instructions_path(member, project_id)}/versions")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_publishing_the_draft_makes_v1_the_current_version(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    await save_draft(editor, project_id, "Be kind.")

    published = await publish(editor, project_id, "First rules")

    assert published.status_code == 201, published.text
    version = published.json()
    assert version["number"] == 1
    assert version["markdown"] == "Be kind."
    assert version["note"] == "First rules"
    assert version["author"] == {"id": editor.member_id, "name": editor.name}
    listed = await history(owner, project_id)
    assert listed["current_version_id"] == version["id"]
    assert [v["number"] for v in listed["versions"]] == [1]


async def current(member: SignedUpMember, project_id: str) -> dict[str, Any] | None:
    """The Current Version, read back from the history."""
    listed = await history(member, project_id)
    found = [v for v in listed["versions"] if v["id"] == listed["current_version_id"]]
    return found[0] if found else None


async def published(
    member: SignedUpMember, project_id: str, markdown: str, note: str
) -> dict[str, Any]:
    await save_draft(member, project_id, markdown)
    response = await publish(member, project_id, note)
    assert response.status_code == 201, response.text
    version: dict[str, Any] = response.json()
    return version


async def test_each_publish_adds_the_next_version_and_the_history_lists_them_newest_first(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    first = await published(owner, project_id, "Be kind.", "First rules")
    second = await published(editor, project_id, "Be kind.\n\nNever quote salaries.", "Salaries")
    # Editing the Draft afterwards changes no Version.
    await save_draft(owner, project_id, "Work in progress")

    listed = await history(editor, project_id)

    assert listed["current_version_id"] == second["id"]
    assert [
        (v["number"], v["markdown"], v["note"], v["author"]["id"], v["previous_version_id"])
        for v in listed["versions"]
    ] == [
        (2, "Be kind.\n\nNever quote salaries.", "Salaries", editor.member_id, first["id"]),
        (1, "Be kind.", "First rules", owner.member_id, None),
    ]
    assert listed["versions"][0]["created_at"] >= listed["versions"][1]["created_at"]
    assert await draft(owner, project_id) == "Work in progress"


async def test_a_new_project_has_no_versions(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    assert await history(owner, project_id) == {"current_version_id": None, "versions": []}


async def test_a_draft_that_matches_the_current_version_is_not_published(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    # Before the first publish, an empty Draft has nothing to publish.
    empty = await publish(owner, project_id, "Nothing yet")
    await published(owner, project_id, "Be kind.", "First rules")
    unchanged = await publish(owner, project_id, "Again")

    for response in (empty, unchanged):
        assert response.status_code == 409
        assert response.json() == {"detail": NOTHING_TO_PUBLISH}
    assert [v["number"] for v in (await history(owner, project_id))["versions"]] == [1]


async def test_clearing_the_instructions_can_be_published(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    await published(owner, project_id, "Be kind.", "First rules")

    cleared = await published(owner, project_id, "", "No shared rules for now")

    assert (cleared["number"], cleared["markdown"]) == (2, "")


@pytest.mark.parametrize("body", [{}, {"note": ""}, {"note": "   "}, {"note": "x" * 501}])
async def test_publishing_takes_a_note(owner: SignedUpMember, body: dict[str, object]) -> None:
    project_id = await create_project(owner)
    await save_draft(owner, project_id, "Be kind.")

    response = await owner.client.post(
        f"{instructions_path(owner, project_id)}/versions", json=body
    )

    assert response.status_code == 422
    assert (await history(owner, project_id))["versions"] == []


async def test_the_note_is_trimmed(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    version = await published(owner, project_id, "Be kind.", "  First rules \n")

    assert version["note"] == "First rules"


# Reverting follows the chain of Current Versions back, never toggling. Each step is "publish"
# (a new Draft text, then publish) or "revert"; the expected value is the Current Version's
# number afterwards.
REVERT_SEQUENCES = [
    pytest.param(["publish", "publish", "revert"], 1, id="publish-publish-revert"),
    pytest.param(
        ["publish", "publish", "publish", "revert", "revert"], 1, id="revert-twice-walks-back"
    ),
    pytest.param(
        ["publish", "publish", "revert", "publish", "revert"], 1, id="reverted-version-is-skipped"
    ),
    pytest.param(
        ["publish", "publish", "publish", "revert", "publish", "revert", "revert"],
        1,
        id="walks-the-chain-not-the-numbers",
    ),
    pytest.param(["publish", "publish", "revert", "publish"], 3, id="publish-after-revert"),
]


@pytest.mark.parametrize(("steps", "expected"), REVERT_SEQUENCES)
async def test_revert_moves_the_current_version_back_along_its_history(
    owner: SignedUpMember, steps: list[str], expected: int
) -> None:
    project_id = await create_project(owner)
    for index, step in enumerate(steps):
        if step == "publish":
            await published(owner, project_id, f"Rules {index}", f"Step {index}")
        else:
            response = await revert(owner, project_id)
            assert response.status_code == 200, response.text

    found = await current(owner, project_id)
    assert found is not None
    assert found["number"] == expected


async def test_revert_returns_the_version_it_moved_to_and_leaves_the_draft_alone(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    first = await published(owner, project_id, "Be kind.", "First rules")
    await published(owner, project_id, "Be curt.", "Shorter")
    await save_draft(owner, project_id, "Draft in progress")

    reverted = await revert(editor, project_id)

    assert reverted.status_code == 200, reverted.text
    assert reverted.json() == first
    assert (await history(owner, project_id))["current_version_id"] == first["id"]
    assert await draft(owner, project_id) == "Draft in progress"


async def test_revert_with_nothing_before_the_current_version_is_refused(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    never_published = await revert(owner, project_id)
    first = await published(owner, project_id, "Be kind.", "First rules")
    only_one = await revert(owner, project_id)
    await published(owner, project_id, "Be curt.", "Shorter")
    await revert(owner, project_id)
    walked_to_the_start = await revert(owner, project_id)

    for response in (never_published, only_one, walked_to_the_start):
        assert response.status_code == 409
        assert response.json() == {"detail": NOTHING_TO_REVERT}
    assert (await history(owner, project_id))["current_version_id"] == first["id"]


async def test_publish_and_revert_are_recorded_as_audit_events(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    first = await published(editor, project_id, "Be kind.", "First rules")
    second = await published(editor, project_id, "Be curt.", "Shorter")
    await revert(owner, project_id)

    published_events = await audit_events(owner, "project.instructions_published")
    reverted_events = await audit_events(owner, "project.instructions_reverted")

    v1 = {"version_id": first["id"], "number": 1}
    v2 = {"version_id": second["id"], "number": 2}
    # Newest first.
    assert [(e["actor"]["id"], e["before"], e["after"]) for e in published_events] == [
        (editor.member_id, {"current_version": v1}, {"current_version": {**v2, "note": "Shorter"}}),
        (
            editor.member_id,
            {"current_version": None},
            {"current_version": {**v1, "note": "First rules"}},
        ),
    ]
    assert [(e["actor"]["id"], e["before"], e["after"]) for e in reverted_events] == [
        (owner.member_id, {"current_version": v2}, {"current_version": v1}),
    ]
    targets = {(e["target"]["type"], e["target"]["id"]) for e in published_events + reverted_events}
    assert targets == {("project", project_id)}


async def test_refused_publishes_and_reverts_record_nothing(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    await publish(owner, project_id, "Nothing yet")
    await revert(owner, project_id)

    assert await audit_events(owner, "project.instructions_published") == []
    assert await audit_events(owner, "project.instructions_reverted") == []


async def test_an_archived_projects_versions_can_be_read_but_not_changed(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    first = await published(owner, project_id, "Be kind.", "First rules")
    await published(owner, project_id, "Be curt.", "Shorter")
    await save_draft(owner, project_id, "Be warm.")
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text

    for response in (await publish(owner, project_id, "Warmer"), await revert(owner, project_id)):
        assert response.status_code == 409
        assert response.json() == {"detail": "This Project is archived. An Owner can restore it."}
    listed = await history(owner, project_id)
    assert [v["number"] for v in listed["versions"]] == [2, 1]
    assert listed["current_version_id"] != first["id"]


async def test_versions_are_not_found_outside_their_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    await published(owner, project_id, "Be kind.", "First rules")
    await published(owner, project_id, "Be curt.", "Shorter")
    stranger = await tenant_factory()
    missing = str(uuid.uuid4())

    for member, target in [(owner, missing), (stranger, project_id)]:
        path = instructions_path(member, target)
        responses = [
            await member.client.get(f"{path}/versions"),
            await member.client.post(f"{path}/versions", json={"note": "Mine now"}),
            await member.client.post(f"{path}/revert"),
        ]
        assert [r.status_code for r in responses] == [404, 404, 404], path
        assert {r.json()["detail"] for r in responses} == {"Not found"}
    found = await current(owner, project_id)
    assert found is not None
    assert found["number"] == 2


async def test_versions_cannot_be_changed_through_the_api(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    version = await published(owner, project_id, "Be kind.", "First rules")
    path = f"{instructions_path(owner, project_id)}/versions"

    attempts = [
        await owner.client.put(path, json={"note": "Rewritten"}),
        await owner.client.patch(path, json={"note": "Rewritten"}),
        await owner.client.delete(path),
        await owner.client.put(f"{path}/{version['id']}", json={"markdown": "Rewritten"}),
        await owner.client.patch(f"{path}/{version['id']}", json={"markdown": "Rewritten"}),
        await owner.client.delete(f"{path}/{version['id']}"),
    ]

    assert [r.status_code for r in attempts] == [405, 405, 405, 404, 404, 404]
    assert (await history(owner, project_id))["versions"] == [version]


async def test_the_database_refuses_to_change_a_version(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """Defence in depth: even a direct UPDATE can't rewrite a Version."""
    project_id = await create_project(owner)
    version = await published(owner, project_id, "Be kind.", "First rules")

    async with app.state.sessionmaker() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                text("UPDATE project_instructions_versions SET markdown = 'x' WHERE id = :id"),
                {"id": version["id"]},
            )

    assert (await history(owner, project_id))["versions"] == [version]


async def test_erasing_the_organisation_removes_its_published_versions(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    """Projects point at Versions, Versions at earlier Versions and their authors, and no
    Version can be updated; erasing the Organisation (``make seed-reset``) still succeeds."""
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    await published(owner, project_id, "Be kind.", "First rules")
    await published(editor, project_id, "Be kind.\n\nNever quote salaries.", "Salaries")
    assert (await revert(owner, project_id)).status_code == 200
    await published(owner, project_id, "Be brief.", "Shorter")

    async with app.state.sessionmaker() as session:
        await erase_organisation(
            session, app.state.ingestion.object_store, uuid.UUID(owner.organisation_id)
        )

    async with app.state.sessionmaker() as session:
        remaining = await session.scalar(
            text("SELECT count(*) FROM project_instructions_versions WHERE organisation_id = :id"),
            {"id": owner.organisation_id},
        )
    assert remaining == 0
    # The Editor's own Organisation, and their account, are untouched.
    assert (await editor.client.get("/api/auth/me")).status_code == 200


async def test_permanently_deleting_the_project_removes_its_published_versions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """03-11's deletion cascade deletes a Project whose Current Version points at a chain of
    Versions; the cascade deletes them and never updates one."""
    project_id = await create_project(owner, "With versions")
    await published(owner, project_id, "Be kind.", "First rules")
    await published(owner, project_id, "Be brief.", "Shorter")
    assert (await revert(owner, project_id)).status_code == 200
    assert (await archive(owner, project_id)).status_code == 200

    response = await delete_permanently(owner, project_id, "With versions")

    assert response.status_code == 202, response.text
    async with app.state.sessionmaker() as session:
        remaining = await session.scalar(
            text("SELECT count(*) FROM project_instructions_versions WHERE project_id = :id"),
            {"id": project_id},
        )
    assert remaining == 0


async def test_concurrent_publishes_of_one_draft_make_one_version_and_a_clear_conflict(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    await save_draft(owner, project_id, "Be kind.")

    responses = await asyncio.gather(
        publish(owner, project_id, "Mine"), publish(editor, project_id, "Theirs")
    )

    assert sorted(r.status_code for r in responses) == [201, 409]
    assert [v["number"] for v in (await history(owner, project_id))["versions"]] == [1]


async def test_concurrent_publishes_of_different_drafts_get_consecutive_numbers(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)

    async def edit_and_publish(index: int) -> None:
        # Each save-and-publish pair may interleave with the others; a publish that finds its
        # text already published is refused, so at least one Version is made per distinct Draft
        # that reached publish first.
        await save_draft(owner, project_id, f"Rules {index}")
        await publish(owner, project_id, f"Step {index}")

    await asyncio.gather(*(edit_and_publish(i) for i in range(5)))

    numbers = [v["number"] for v in (await history(owner, project_id))["versions"]]
    assert numbers == list(range(len(numbers), 0, -1))
    assert numbers


# The migration from spec 04's single Instructions field


def _migrate(direction: str, revision: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    getattr(command, direction)(config, revision)


async def test_the_migration_turns_existing_instructions_into_the_draft_and_v1(
    app: FastAPI, owner: SignedUpMember
) -> None:
    with_rules = await create_project(owner, "With rules")
    await save_draft(owner, with_rules, "Be kind.")
    without_rules = await create_project(owner, "Without rules")
    # Back to spec 04's schema, where the Instructions were one field; then migrate forward.
    await asyncio.to_thread(_migrate, "downgrade", "0024_re_embed_jobs")
    try:
        await asyncio.to_thread(_migrate, "upgrade", "head")
    finally:
        # The pool's connections cached statements for the tables that were dropped.
        await app.state.engine.dispose()

    listed = await history(owner, with_rules)
    (v1,) = listed["versions"]
    assert listed["current_version_id"] == v1["id"]
    assert (v1["number"], v1["markdown"], v1["author"], v1["previous_version_id"]) == (
        1,
        "Be kind.",
        None,
        None,
    )
    assert v1["note"] == "The Instructions as they were when Versions were introduced."
    assert await draft(owner, with_rules) == "Be kind."
    # Empty Instructions had nothing to version.
    assert await history(owner, without_rules) == {"current_version_id": None, "versions": []}
    # The migrated v1 is an ordinary Version: publishing builds on it and reverting returns to it.
    v2 = await published(owner, with_rules, "Be curt.", "Shorter")
    assert (v2["number"], v2["previous_version_id"]) == (2, v1["id"])
    reverted = await revert(owner, with_rules)
    assert reverted.json() == v1
