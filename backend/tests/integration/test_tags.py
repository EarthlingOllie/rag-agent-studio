"""API seam: an Editor creates, renames and deletes a Project's Tags, applies several Tags to a
Document and bulk-applies Tags to many Documents, and filters the Document list by name,
status and Tag. Everything is observed back through the API."""

from typing import Any

import httpx
from fastapi import FastAPI

from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project, documents, project_path, upload


async def _create_tag(member: SignedUpMember, project_id: str, name: str) -> dict[str, Any]:
    response = await member.client.post(
        f"{project_path(member, project_id)}/tags", json={"name": name}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _tags(member: SignedUpMember, project_id: str) -> list[dict[str, Any]]:
    response = await member.client.get(f"{project_path(member, project_id)}/tags")
    assert response.status_code == 200, response.text
    listed: list[dict[str, Any]] = response.json()
    return listed


async def test_an_editor_creates_tags_listed_by_name(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)

    hr = await _create_tag(editor, project_id, "  HR ")
    await _create_tag(editor, project_id, "benefits")
    await _create_tag(editor, project_id, "Onboarding")

    assert (hr["name"], hr["document_count"]) == ("HR", 0)
    assert [t["name"] for t in await _tags(editor, project_id)] == ["benefits", "HR", "Onboarding"]


async def test_tag_names_are_unique_in_a_project_ignoring_case(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    other_project = await create_project(owner, "Sales")
    await _create_tag(owner, project_id, "HR")

    duplicate = await owner.client.post(
        f"{project_path(owner, project_id)}/tags", json={"name": "hr"}
    )
    elsewhere = await owner.client.post(
        f"{project_path(owner, other_project)}/tags", json={"name": "hr"}
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "This Project already has a Tag with that name."}
    assert elsewhere.status_code == 201
    assert [t["name"] for t in await _tags(owner, project_id)] == ["HR"]


async def test_a_blank_or_overlong_tag_name_is_refused(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    for name in ("   ", "x" * 51):
        response = await owner.client.post(
            f"{project_path(owner, project_id)}/tags", json={"name": name}
        )
        assert response.status_code == 422

    assert await _tags(owner, project_id) == []


async def test_an_editor_renames_a_tag_and_documents_keep_it(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    tag = await _create_tag(owner, project_id, "HR")
    await _create_tag(owner, project_id, "Sales")
    document = await upload(app, owner, project_id, "handbook.md", b"# Handbook\n\nHello.")
    await _set_tags(owner, project_id, document["id"], [tag["id"]])

    renamed = await owner.client.patch(
        f"{project_path(owner, project_id)}/tags/{tag['id']}", json={"name": "People"}
    )
    recased = await owner.client.patch(
        f"{project_path(owner, project_id)}/tags/{tag['id']}", json={"name": "people"}
    )
    taken = await owner.client.patch(
        f"{project_path(owner, project_id)}/tags/{tag['id']}", json={"name": "SALES"}
    )

    assert renamed.status_code == 200
    assert (renamed.json()["name"], renamed.json()["document_count"]) == ("People", 1)
    assert (recased.status_code, recased.json()["name"]) == (200, "people")
    assert taken.status_code == 409
    assert [t["name"] for t in await _tags(owner, project_id)] == ["people", "Sales"]
    (listed,) = await documents(owner, project_id)
    assert listed["tags"] == [{"id": tag["id"], "name": "people"}]


async def test_deleting_a_tag_takes_it_off_documents_which_stay(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    hr = await _create_tag(owner, project_id, "HR")
    sales = await _create_tag(owner, project_id, "Sales")
    document = await upload(app, owner, project_id, "handbook.md", b"# Handbook\n\nHello.")
    await _set_tags(owner, project_id, document["id"], [hr["id"], sales["id"]])

    deleted = await owner.client.delete(f"{project_path(owner, project_id)}/tags/{hr['id']}")
    again = await owner.client.delete(f"{project_path(owner, project_id)}/tags/{hr['id']}")

    assert deleted.status_code == 204
    assert (again.status_code, again.json()) == (404, {"detail": "Not found"})
    assert [t["name"] for t in await _tags(owner, project_id)] == ["Sales"]
    (listed,) = await documents(owner, project_id)
    assert listed["tags"] == [{"id": sales["id"], "name": "Sales"}]


async def test_an_unknown_tag_cannot_be_renamed(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    other_project = await create_project(owner, "Sales")
    elsewhere = await _create_tag(owner, other_project, "HR")

    response = await owner.client.patch(
        f"{project_path(owner, project_id)}/tags/{elsewhere['id']}", json={"name": "People"}
    )

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})
    assert [t["name"] for t in await _tags(owner, other_project)] == ["HR"]


async def _set_tags(
    member: SignedUpMember, project_id: str, document_id: str, tag_ids: list[str]
) -> httpx.Response:
    response = await member.client.put(
        f"{project_path(member, project_id)}/documents/{document_id}/tags",
        json={"tag_ids": tag_ids},
    )
    assert response.status_code == 200, response.text
    return response


async def test_several_tags_are_applied_to_a_document_and_can_be_cleared(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    onboarding = await _create_tag(editor, project_id, "Onboarding")
    hr = await _create_tag(editor, project_id, "HR")
    benefits = await _create_tag(editor, project_id, "benefits")
    document = await upload(app, editor, project_id, "handbook.md", b"# Handbook\n\nHello.")

    first = await _set_tags(editor, project_id, document["id"], [onboarding["id"], hr["id"]])
    second = await _set_tags(editor, project_id, document["id"], [hr["id"], benefits["id"]])

    assert [t["name"] for t in first.json()] == ["HR", "Onboarding"]
    assert [t["name"] for t in second.json()] == ["benefits", "HR"]
    (listed,) = await documents(editor, project_id)
    assert [t["name"] for t in listed["tags"]] == ["benefits", "HR"]
    counts = {t["name"]: t["document_count"] for t in await _tags(editor, project_id)}
    assert counts == {"benefits": 1, "HR": 1, "Onboarding": 0}

    cleared = await _set_tags(editor, project_id, document["id"], [])

    assert cleared.json() == []
    (listed,) = await documents(editor, project_id)
    assert listed["tags"] == []


async def test_a_tag_from_another_project_cannot_be_applied(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    other_project = await create_project(owner, "Sales")
    own = await _create_tag(owner, project_id, "HR")
    foreign = await _create_tag(owner, other_project, "Pricing")
    document = await upload(app, owner, project_id, "handbook.md", b"# Handbook\n\nHello.")
    other_document = await upload(app, owner, other_project, "deck.md", b"# Deck\n\nHi.")
    path = project_path(owner, project_id)

    with_foreign_tag = await owner.client.put(
        f"{path}/documents/{document['id']}/tags", json={"tag_ids": [own["id"], foreign["id"]]}
    )
    on_foreign_document = await owner.client.put(
        f"{path}/documents/{other_document['id']}/tags", json={"tag_ids": [own["id"]]}
    )

    assert with_foreign_tag.status_code == 422
    assert with_foreign_tag.json() == {
        "detail": "One or more of these Tags aren't in this Project."
    }
    assert (on_foreign_document.status_code, on_foreign_document.json()) == (
        404,
        {"detail": "Not found"},
    )
    assert [d["tags"] for d in await documents(owner, project_id)] == [[]]
    assert [d["tags"] for d in await documents(owner, other_project)] == [[]]


async def _bulk(member: SignedUpMember, project_id: str, **body: list[str]) -> httpx.Response:
    return await member.client.post(f"{project_path(member, project_id)}/documents/tags", json=body)


async def test_tags_are_bulk_applied_to_and_removed_from_many_documents(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    hr = await _create_tag(owner, project_id, "HR")
    policy = await _create_tag(owner, project_id, "Policy")
    draft = await _create_tag(owner, project_id, "Draft")
    a = await upload(app, owner, project_id, "a.md", b"# A\n\nOne.")
    b = await upload(app, owner, project_id, "b.md", b"# B\n\nTwo.")
    c = await upload(app, owner, project_id, "c.md", b"# C\n\nThree.")
    await _set_tags(owner, project_id, a["id"], [hr["id"], draft["id"]])

    applied = await _bulk(
        owner, project_id, document_ids=[a["id"], b["id"]], add=[hr["id"], policy["id"]]
    )

    assert applied.status_code == 204
    tags = {d["name"]: [t["name"] for t in d["tags"]] for d in await documents(owner, project_id)}
    assert tags == {"a.md": ["Draft", "HR", "Policy"], "b.md": ["HR", "Policy"], "c.md": []}

    removed = await _bulk(
        owner, project_id, document_ids=[a["id"], c["id"]], add=[draft["id"]], remove=[hr["id"]]
    )

    assert removed.status_code == 204
    tags = {d["name"]: [t["name"] for t in d["tags"]] for d in await documents(owner, project_id)}
    assert tags == {"a.md": ["Draft", "Policy"], "b.md": ["HR", "Policy"], "c.md": ["Draft"]}
    counts = {t["name"]: t["document_count"] for t in await _tags(owner, project_id)}
    assert counts == {"Draft": 2, "HR": 1, "Policy": 2}


async def test_bulk_tagging_refuses_documents_or_tags_outside_the_project(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    other_project = await create_project(owner, "Sales")
    hr = await _create_tag(owner, project_id, "HR")
    foreign_tag = await _create_tag(owner, other_project, "Pricing")
    document = await upload(app, owner, project_id, "a.md", b"# A\n\nOne.")
    foreign_document = await upload(app, owner, other_project, "b.md", b"# B\n\nTwo.")

    foreign_doc = await _bulk(
        owner, project_id, document_ids=[document["id"], foreign_document["id"]], add=[hr["id"]]
    )
    foreign_add = await _bulk(
        owner, project_id, document_ids=[document["id"]], add=[foreign_tag["id"]]
    )
    foreign_remove = await _bulk(
        owner, project_id, document_ids=[document["id"]], remove=[foreign_tag["id"]]
    )
    no_documents = await _bulk(owner, project_id, document_ids=[], add=[hr["id"]])

    assert (foreign_doc.status_code, foreign_doc.json()) == (
        422,
        {"detail": "One or more of these Documents aren't in this Project."},
    )
    assert foreign_add.status_code == foreign_remove.status_code == 422
    assert foreign_add.json() == {"detail": "One or more of these Tags aren't in this Project."}
    assert no_documents.status_code == 422
    assert [d["tags"] for d in await documents(owner, project_id)] == [[]]
    assert [d["tags"] for d in await documents(owner, other_project)] == [[]]


async def test_an_archived_projects_tags_can_be_read_but_not_changed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    hr = await _create_tag(owner, project_id, "HR")
    document = await upload(app, owner, project_id, "a.md", b"# A\n\nOne.")
    await _set_tags(owner, project_id, document["id"], [hr["id"]])
    path = project_path(owner, project_id)
    archived = await owner.client.post(f"{path}/archive")
    assert archived.status_code == 200

    attempts = [
        await owner.client.post(f"{path}/tags", json={"name": "Sales"}),
        await owner.client.patch(f"{path}/tags/{hr['id']}", json={"name": "People"}),
        await owner.client.delete(f"{path}/tags/{hr['id']}"),
        await owner.client.put(f"{path}/documents/{document['id']}/tags", json={"tag_ids": []}),
        await _bulk(owner, project_id, document_ids=[document["id"]], remove=[hr["id"]]),
    ]

    assert [(r.status_code, r.json()["detail"]) for r in attempts] == [
        (409, "This Project is archived. An Owner can restore it.")
    ] * 5
    assert [(t["name"], t["document_count"]) for t in await _tags(owner, project_id)] == [("HR", 1)]


async def _names(
    member: SignedUpMember, project_id: str, params: list[tuple[str, str]]
) -> list[str]:
    response = await member.client.get(
        f"{project_path(member, project_id)}/documents", params=tuple(params)
    )
    assert response.status_code == 200, response.text
    return sorted(d["name"] for d in response.json())


async def test_the_document_list_filters_by_name_status_and_tag(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    hr = await _create_tag(owner, project_id, "HR")
    policy = await _create_tag(owner, project_id, "Policy")
    leave = await upload(app, owner, project_id, "Leave policy.md", b"# Leave\n\nDays.")
    expenses = await upload(app, owner, project_id, "expenses_100%.md", b"# Expenses\n\nClaims.")
    await upload(app, owner, project_id, "sales deck.md", b"# Sales\n\nDeck.")
    # The converter fails on this one, so it ends Failed.
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    await upload(app, owner, project_id, "broken POLICY.txt", b"Broken.")
    app.state.ingestion.converter.failure = None
    await _set_tags(owner, project_id, leave["id"], [hr["id"], policy["id"]])
    await _set_tags(owner, project_id, expenses["id"], [hr["id"]])

    everything = await _names(owner, project_id, [])
    by_name = await _names(owner, project_id, [("q", "  policy ")])
    literal_wildcards = await _names(owner, project_id, [("q", "_100%")])
    no_wildcard_match = await _names(owner, project_id, [("q", "%")])
    failed = await _names(owner, project_id, [("status", "failed")])
    ready_or_failed = await _names(owner, project_id, [("status", "ready"), ("status", "failed")])
    tagged_hr = await _names(owner, project_id, [("tag_id", hr["id"])])
    tagged_both = await _names(owner, project_id, [("tag_id", hr["id"]), ("tag_id", policy["id"])])
    combined = await _names(
        owner, project_id, [("q", "EXPENSES"), ("status", "ready"), ("tag_id", hr["id"])]
    )
    nothing = await _names(
        owner, project_id, [("q", "leave"), ("tag_id", policy["id"]), ("status", "queued")]
    )

    assert len(everything) == 4
    assert by_name == ["Leave policy.md", "broken POLICY.txt"]
    assert literal_wildcards == ["expenses_100%.md"]
    assert no_wildcard_match == ["expenses_100%.md"]
    assert failed == ["broken POLICY.txt"]
    assert ready_or_failed == everything
    assert tagged_hr == ["Leave policy.md", "expenses_100%.md"]
    assert tagged_both == ["Leave policy.md"]
    assert combined == ["expenses_100%.md"]
    assert nothing == []


async def test_an_unknown_status_filter_is_refused(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    response = await owner.client.get(
        f"{project_path(owner, project_id)}/documents", params={"status": "archived"}
    )

    assert response.status_code == 422
