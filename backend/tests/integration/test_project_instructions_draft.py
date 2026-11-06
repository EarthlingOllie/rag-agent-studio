"""API seam: the Project Instructions Draft's revision. A save made on a Draft someone has
since changed is refused with 409 and the latest Draft, so nobody silently overwrites a
colleague's edits."""

import httpx

from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project
from tests.integration.test_project_instructions_versions import instructions_path

STALE = (
    "Someone else saved these Instructions after you opened them. Load their changes, or save "
    "yours over them."
)


async def save(
    member: SignedUpMember, project_id: str, markdown: str, base_revision: int | None = None
) -> httpx.Response:
    params = {} if base_revision is None else {"base_revision": base_revision}
    return await member.client.put(
        instructions_path(member, project_id), params=params, json={"markdown": markdown}
    )


async def test_each_change_moves_the_draft_to_its_next_revision(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    fetched = await owner.client.get(instructions_path(owner, project_id))
    assert fetched.json() == {"markdown": "", "revision": 1}

    first = await save(owner, project_id, "Be kind.", base_revision=1)
    same = await save(owner, project_id, "Be kind.", base_revision=2)

    assert first.json() == {"markdown": "Be kind.", "revision": 2}
    # Saving the same text changes nothing, so the revision stays.
    assert same.json() == {"markdown": "Be kind.", "revision": 2}


async def test_saving_stale_instructions_is_refused_with_the_latest_draft(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    assert (await save(editor, project_id, "Theirs", base_revision=1)).status_code == 200

    mine = await save(owner, project_id, "Mine", base_revision=1)

    assert mine.status_code == 409, mine.text
    assert mine.json() == {"detail": STALE, "latest": {"markdown": "Theirs", "revision": 2}}
    fetched = await owner.client.get(instructions_path(owner, project_id))
    assert fetched.json()["markdown"] == "Theirs"
    over = await save(owner, project_id, "Mine", base_revision=2)
    assert over.json() == {"markdown": "Mine", "revision": 3}


async def test_a_save_without_a_base_revision_replaces_the_draft(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    await save(owner, project_id, "One", base_revision=1)

    response = await save(owner, project_id, "Two")

    assert response.json() == {"markdown": "Two", "revision": 3}
