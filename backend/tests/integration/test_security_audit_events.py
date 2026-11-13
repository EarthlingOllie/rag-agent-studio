"""AGT-R2-2: security-relevant changes are Audit Events. API seam: an Editor uploads or replaces
a Document, changes the model, a Provider Credential, the Guardrail settings or the avatar of
an Agent's Draft, or publishes it; the Owner reads the Audit log."""

import copy
from typing import Any

from fastapi import FastAPI

from tests.agents import FULL_DEFAULT_DRAFT, create_agent, save_draft, use_default_model
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project, replace, upload
from tests.integration.test_agent_versions import published
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    audit_events,
)

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
HANDBOOK_SHA256 = "39dac3beae4becd713da78dff79a0a43f65f59d44dcd64bd957d9b9e2757824e"
NEWER = b"# Handbook\n\nEveryone gets 26 days of annual leave a year."
NEWER_SHA256 = "a7db39c15ef4ded7cbf5e71d49c54ec1d98df7045c8ff2179b0cdbe2976dbe08"
DRAFT_CHANGED = "agent.draft_settings_changed"
AVATAR = "https://cdn.example.com/helper.png"


def summary(event: dict[str, Any]) -> tuple[Any, ...]:
    return event["actor"]["id"], event["target"], event["before"], event["after"]


async def test_uploading_a_document_is_audited_with_its_file_name(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)

    document = await upload(app, editor, project_id, "handbook.md", HANDBOOK)

    (event,) = await audit_events(owner, "document.created")
    assert summary(event) == (
        editor.member_id,
        {"type": "document", "id": document["id"]},
        None,
        {
            "project_id": project_id,
            "name": "handbook.md",
            "mime_type": "text/markdown",
            "size_bytes": len(HANDBOOK),
            "content_hash": HANDBOOK_SHA256,
        },
    )


async def test_replacing_a_document_is_audited_with_both_file_names(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    response = await replace(app, editor, project_id, document["id"], "handbook-2027.md", NEWER)

    assert response.status_code == 202, response.text
    (event,) = await audit_events(owner, "document.replaced")
    assert summary(event) == (
        editor.member_id,
        {"type": "document", "id": document["id"]},
        {"name": "handbook.md", "content_hash": HANDBOOK_SHA256, "edition": 1},
        {
            "project_id": project_id,
            "name": "handbook-2027.md",
            "mime_type": "text/markdown",
            "size_bytes": len(NEWER),
            "content_hash": NEWER_SHA256,
            "edition": 2,
        },
    )


async def test_changing_a_drafts_model_credential_guardrails_or_avatar_is_audited(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    first = await use_default_model(owner)
    second = (await added(owner, provider="openai", api_key=OPENAI_KEY))["id"]
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    saves = [
        await save_draft(
            editor,
            project_id,
            agent_id,
            {"behaviour": {"model": {"credential_id": first, "model": "gpt-4.1-mini"}}},
        ),
        await save_draft(
            editor,
            project_id,
            agent_id,
            {
                "behaviour": {"model": {"credential_id": second, "model": "gpt-4.1"}},
                "experience": {"avatar_url": AVATAR},
                "guardrails": {
                    "classifier": {"credential_id": second, "model": "gpt-4.1-mini"},
                    "fail_mode": "open",
                },
            },
        ),
    ]

    assert [s.status_code for s in saves] == [200, 200]
    events = await audit_events(owner, DRAFT_CHANGED)
    target = {"type": "agent", "id": agent_id}
    # Newest first; only the settings that changed.
    assert [summary(e) for e in events] == [
        (
            editor.member_id,
            target,
            {
                "model": {"credential_id": first, "model": "gpt-4.1-mini"},
                "guardrail_classifier": None,
                "guardrail_fail_mode": "closed",
                "avatar_url": None,
            },
            {
                "model": {"credential_id": second, "model": "gpt-4.1"},
                "guardrail_classifier": {"credential_id": second, "model": "gpt-4.1-mini"},
                "guardrail_fail_mode": "open",
                "avatar_url": AVATAR,
            },
        ),
        (
            editor.member_id,
            target,
            {"model": None},
            {"model": {"credential_id": first, "model": "gpt-4.1-mini"}},
        ),
    ]


async def test_changing_a_drafts_reranker_is_audited(owner: SignedUpMember) -> None:
    voyage = (await added(owner, provider="voyage", api_key=VOYAGE_KEY))["id"]
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    reranker = {"credential_id": voyage, "model": "rerank-2.5"}

    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {"reranker": reranker}})

    assert saved.status_code == 200, saved.text
    (event,) = await audit_events(owner, DRAFT_CHANGED)
    assert (event["before"], event["after"]) == ({"reranker": None}, {"reranker": reranker})


async def test_a_draft_save_that_leaves_those_settings_alone_is_not_audited(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    saved = await save_draft(
        owner, project_id, agent_id, {"behaviour": {"system_prompt": "Be kind."}}
    )

    assert saved.status_code == 200, saved.text
    assert await audit_events(owner, DRAFT_CHANGED) == []


async def test_publishing_records_a_snapshot_of_the_published_config(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    draft = {"behaviour": {"system_prompt": "Be kind."}, "experience": {"avatar_url": AVATAR}}
    assert (await save_draft(owner, project_id, agent_id, draft)).status_code == 200

    await published(owner, project_id, agent_id)

    expected = copy.deepcopy(FULL_DEFAULT_DRAFT)
    expected["behaviour"]["system_prompt"] = "Be kind."
    expected["experience"]["avatar_url"] = AVATAR
    (event,) = await audit_events(owner, "agent.published")
    assert event["after"]["config"] == expected
