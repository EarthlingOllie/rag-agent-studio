"""API seam: an Editor edits every group of an Agent's Draft (Behaviour, Retrieval, Experience
and Guardrails). Saving validates the Draft against the capability registry and the Project's
Tags, and registers the credentials it names as Credential references."""

import copy
import uuid
from typing import Any

import pytest

from tests.agents import FULL_DEFAULT_DRAFT, agents_path, create_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path
from tests.integration.test_provider_credentials import (
    ANTHROPIC_KEY,
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    credentials_path,
)


def full_draft(openai: str, voyage: str, anthropic: str, tag_id: str) -> dict[str, Any]:
    """A Draft that sets every field away from its default."""
    return {
        "behaviour": {
            "system_prompt": "# Role\n\nAnswer from the handbook.",
            "model": {"credential_id": anthropic, "model": "claude-haiku-4-5"},
            "temperature": 0.2,
            "max_output_tokens": 600,
            "remembered_turns": 3,
            "fallback_text": "I can't find that in the handbook.",
        },
        "retrieval": {
            "top_k": 8,
            "hybrid_weight": 0.3,
            "min_score": 0.25,
            "tag_ids": [tag_id],
            "reranker": {"credential_id": voyage, "model": "rerank-2.5-lite"},
            "citations": False,
            "mode": "agentic",
            "search_limit": 5,
        },
        "experience": {
            "display_name": "Hana from HR",
            "avatar_url": "https://cdn.example.com/hana.png",
            "greeting": "Hi! Ask me about leave, pay or benefits.",
            "starter_questions": ["How much leave do I get?", "When is payday?"],
            "ui_text": {
                "send_button": "Ask",
                "rate_conversation": "How did Hana do?",
                "unavailable_message": "Hana is on a break. Try again soon.",
                "searching_status": "Hana is looking that up…",
            },
            "rating_prompt_after": 5,
        },
        "guardrails": {
            "input_mode": "warn",
            "classifier": {"credential_id": openai, "model": "gpt-4.1-mini"},
            "fail_mode": "open",
            "refusal_text": "I can only help with HR questions.",
        },
    }


async def create_tag(member: SignedUpMember, project_id: str, name: str = "HR") -> str:
    response = await member.client.post(
        f"{project_path(member, project_id)}/tags", json={"name": name}
    )
    assert response.status_code == 201, response.text
    tag_id: str = response.json()["id"]
    return tag_id


async def three_credentials(owner: SignedUpMember) -> tuple[str, str, str]:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY, name="OpenAI")
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY, name="Voyage")
    anthropic = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    return openai["id"], voyage["id"], anthropic["id"]


async def test_a_new_agents_draft_has_every_group_at_its_defaults(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    agent = await create_agent(owner, project_id)

    assert agent["draft"] == FULL_DEFAULT_DRAFT


async def test_an_editor_sets_every_setting_and_reads_it_back_exactly(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    openai, voyage, anthropic = await three_credentials(owner)
    project_id = await create_project(editor)
    tag_id = await create_tag(editor, project_id)
    agent = await create_agent(editor, project_id)
    draft = full_draft(openai, voyage, anthropic, tag_id)

    saved = await save_draft(editor, project_id, agent["id"], draft)

    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"] == draft
    fetched = await editor.client.get(agents_path(editor, project_id, agent["id"]))
    assert fetched.json()["draft"] == draft


async def test_settings_can_be_cleared_back_to_following_the_default_model(
    owner: SignedUpMember,
) -> None:
    openai, voyage, anthropic = await three_credentials(owner)
    project_id = await create_project(owner)
    tag_id = await create_tag(owner, project_id)
    agent = await create_agent(owner, project_id)
    await save_draft(owner, project_id, agent["id"], full_draft(openai, voyage, anthropic, tag_id))

    cleared = await save_draft(owner, project_id, agent["id"], FULL_DEFAULT_DRAFT)

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["draft"] == FULL_DEFAULT_DRAFT


def _set(draft: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    changed = copy.deepcopy(draft)
    *groups, field = path.split(".")
    target = changed
    for group in groups:
        target = target[group]
    target[field] = value
    return changed


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("behaviour.temperature", -0.1),
        ("behaviour.temperature", 1.01),
        ("behaviour.max_output_tokens", 0),
        ("behaviour.max_output_tokens", 8193),
        ("behaviour.remembered_turns", -1),
        ("behaviour.remembered_turns", 21),
        ("behaviour.fallback_text", ""),
        ("retrieval.top_k", 21),
        ("retrieval.hybrid_weight", 1.5),
        ("retrieval.min_score", -0.5),
        ("retrieval.tag_ids", ["not-a-uuid"]),
        ("retrieval.mode", "psychic"),
        ("retrieval.search_limit", 0),
        ("retrieval.search_limit", 6),
        ("experience.display_name", "x" * 101),
        ("experience.avatar_url", "http://cdn.example.com/plain-http.png"),
        ("experience.avatar_url", "javascript:alert(1)"),
        ("experience.greeting", "x" * 1001),
        ("experience.starter_questions", ["one", "two", "three", "four", "five", "six", "7"]),
        ("experience.starter_questions", ["   "]),
        ("experience.starter_questions", ["x" * 201]),
        ("experience.ui_text", {"send_button": ""}),
        ("experience.ui_text", {"send_button": "x" * 201}),
        ("experience.ui_text", {"searching_status": "x" * 201}),
        ("experience.ui_text", {"close_button": "Bye"}),
        ("experience.rating_prompt_after", -1),
        ("experience.rating_prompt_after", 51),
        ("guardrails.input_mode", "shout"),
        ("guardrails.fail_mode", "sideways"),
        ("guardrails.refusal_text", ""),
        ("behaviour.model", {"credential_id": str(uuid.uuid4())}),
    ],
)
async def test_out_of_range_settings_are_refused_with_where_and_why(
    owner: SignedUpMember, path: str, value: Any
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)

    refused = await save_draft(
        owner, project_id, agent["id"], _set(FULL_DEFAULT_DRAFT, path, value)
    )

    assert refused.status_code == 422
    (error, *_) = refused.json()["detail"]
    assert error["loc"][: 1 + len(path.split("."))] == ["body", *path.split(".")]
    assert error["msg"]
    fetched = await owner.client.get(agents_path(owner, project_id, agent["id"]))
    assert fetched.json()["draft"] == FULL_DEFAULT_DRAFT


async def test_starter_questions_and_ui_text_are_trimmed(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = _set(FULL_DEFAULT_DRAFT, "experience.starter_questions", ["  When is payday?  "])
    draft = _set(draft, "experience.ui_text", {"send_button": " Ask "})

    saved = await save_draft(owner, project_id, agent["id"], draft)

    assert saved.json()["draft"]["experience"]["starter_questions"] == ["When is payday?"]
    assert saved.json()["draft"]["experience"]["ui_text"] == {
        "send_button": "Ask",
        "rate_conversation": None,
        "unavailable_message": None,
        "searching_status": None,
    }


@pytest.mark.parametrize(
    ("path", "choice", "loc", "message"),
    [
        (
            "behaviour.model",
            ("voyage", "voyage-3.5"),
            ["body", "behaviour", "model", "credential_id"],
            "This credential can't be used for chat.",
        ),
        (
            "behaviour.model",
            ("openai", "claude-haiku-4-5"),
            ["body", "behaviour", "model", "model"],
            "OpenAI doesn't offer claude-haiku-4-5 for chat.",
        ),
        (
            "retrieval.reranker",
            ("openai", "gpt-4.1-mini"),
            ["body", "retrieval", "reranker", "credential_id"],
            "This credential can't be used for rerank.",
        ),
        (
            "retrieval.reranker",
            ("voyage", "rerank-1"),
            ["body", "retrieval", "reranker", "model"],
            "Voyage AI doesn't offer rerank-1 for rerank.",
        ),
        (
            "guardrails.classifier",
            ("voyage", "rerank-2.5"),
            ["body", "guardrails", "classifier", "credential_id"],
            "This credential can't be used for chat.",
        ),
        (
            "guardrails.classifier",
            ("anthropic", "gpt-4.1"),
            ["body", "guardrails", "classifier", "model"],
            "Anthropic doesn't offer gpt-4.1 for chat.",
        ),
    ],
)
async def test_a_model_the_credential_doesnt_offer_is_refused_with_a_clear_message(
    owner: SignedUpMember,
    path: str,
    choice: tuple[str, str],
    loc: list[str],
    message: str,
) -> None:
    openai, voyage, anthropic = await three_credentials(owner)
    credential = {"openai": openai, "voyage": voyage, "anthropic": anthropic}[choice[0]]
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = _set(FULL_DEFAULT_DRAFT, path, {"credential_id": credential, "model": choice[1]})

    refused = await save_draft(owner, project_id, agent["id"], draft)

    assert refused.status_code == 422
    assert refused.json() == {"detail": [{"loc": loc, "msg": message, "type": "model_unavailable"}]}


async def test_a_credential_from_elsewhere_is_refused(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    stranger = await tenant_factory()
    theirs = await added(stranger, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)

    for credential_id in [theirs["id"], str(uuid.uuid4())]:
        draft = _set(
            FULL_DEFAULT_DRAFT,
            "behaviour.model",
            {"credential_id": credential_id, "model": "gpt-4.1-mini"},
        )
        refused = await save_draft(owner, project_id, agent["id"], draft)

        assert refused.status_code == 422
        assert refused.json()["detail"] == [
            {
                "loc": ["body", "behaviour", "model", "credential_id"],
                "msg": "Choose a Provider Credential from this Organisation.",
                "type": "unknown_credential",
            }
        ]


async def test_every_problem_is_reported_at_once(owner: SignedUpMember) -> None:
    openai, voyage, _ = await three_credentials(owner)
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = _set(
        FULL_DEFAULT_DRAFT, "behaviour.model", {"credential_id": voyage, "model": "voyage-3.5"}
    )
    draft = _set(draft, "retrieval.reranker", {"credential_id": openai, "model": "gpt-4.1"})

    refused = await save_draft(owner, project_id, agent["id"], draft)

    assert [error["loc"] for error in refused.json()["detail"]] == [
        ["body", "behaviour", "model", "credential_id"],
        ["body", "retrieval", "reranker", "credential_id"],
    ]


async def test_tags_must_belong_to_the_agents_project(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    other_project_id = await create_project(owner, "Sales")
    own_tag = await create_tag(owner, project_id, "HR")
    other_tag = await create_tag(owner, other_project_id, "Sales")
    agent = await create_agent(owner, project_id)
    missing = str(uuid.uuid4())
    draft = _set(FULL_DEFAULT_DRAFT, "retrieval.tag_ids", [own_tag, other_tag, missing])

    refused = await save_draft(owner, project_id, agent["id"], draft)

    assert refused.status_code == 422
    assert refused.json()["detail"] == [
        {
            "loc": ["body", "retrieval", "tag_ids", index],
            "msg": "Choose Tags from this Project.",
            "type": "unknown_tag",
        }
        for index in (1, 2)
    ]
    duplicate = await save_draft(
        owner, project_id, agent["id"], _set(FULL_DEFAULT_DRAFT, "retrieval.tag_ids", [own_tag] * 2)
    )
    assert duplicate.json()["draft"]["retrieval"]["tag_ids"] == [own_tag]


async def test_deleting_a_tag_takes_it_out_of_every_draft_that_scoped_to_it(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    hr = await create_tag(owner, project_id, "HR")
    policies = await create_tag(owner, project_id, "Policies")
    agent = await create_agent(owner, project_id)
    scoped = _set(FULL_DEFAULT_DRAFT, "retrieval.tag_ids", [hr, policies])
    assert (await save_draft(owner, project_id, agent["id"], scoped)).status_code == 200

    deleted = await owner.client.delete(f"{project_path(owner, project_id)}/tags/{hr}")
    assert deleted.status_code == 204, deleted.text

    read = await owner.client.get(agents_path(owner, project_id, agent["id"]))
    assert read.json()["draft"]["retrieval"]["tag_ids"] == [policies]
    resaved = await save_draft(owner, project_id, agent["id"], read.json()["draft"])
    assert resaved.status_code == 200, resaved.text


async def test_credentials_an_agent_uses_cant_be_deleted(owner: SignedUpMember) -> None:
    openai, voyage, anthropic = await three_credentials(owner)
    project_id = await create_project(owner)
    tag_id = await create_tag(owner, project_id)
    agent = await create_agent(owner, project_id, "HR helper")
    other = await create_agent(owner, project_id, "Benefits FAQ")
    await save_draft(owner, project_id, agent["id"], full_draft(openai, voyage, anthropic, tag_id))
    both = _set(
        FULL_DEFAULT_DRAFT, "behaviour.model", {"credential_id": openai, "model": "gpt-4.1"}
    )
    await save_draft(owner, project_id, other["id"], both)

    refused = {
        name: await owner.client.delete(credentials_path(owner.organisation_id, credential))
        for name, credential in [("openai", openai), ("voyage", voyage), ("anthropic", anthropic)]
    }

    assert {name: response.status_code for name, response in refused.items()} == {
        "openai": 409,
        "voyage": 409,
        "anthropic": 409,
    }
    assert refused["openai"].json()["references"] == [
        {"kind": "agent", "id": other["id"], "name": "Benefits FAQ (model)"},
        {"kind": "agent", "id": agent["id"], "name": "HR helper (Guardrail classifier)"},
    ]
    assert refused["voyage"].json()["references"] == [
        {"kind": "agent", "id": agent["id"], "name": "HR helper (reranker)"}
    ]
    assert refused["anthropic"].json()["references"] == [
        {"kind": "agent", "id": agent["id"], "name": "HR helper (model)"}
    ]

    # Clearing the settings releases the credentials.
    await save_draft(owner, project_id, agent["id"], FULL_DEFAULT_DRAFT)
    await save_draft(owner, project_id, other["id"], FULL_DEFAULT_DRAFT)
    for credential in (openai, voyage, anthropic):
        deleted = await owner.client.delete(credentials_path(owner.organisation_id, credential))
        assert deleted.status_code == 204


async def test_references_are_only_reported_in_their_own_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    await save_draft(
        owner,
        project_id,
        agent["id"],
        _set(
            FULL_DEFAULT_DRAFT,
            "behaviour.model",
            {"credential_id": openai["id"], "model": "gpt-4.1"},
        ),
    )
    stranger = await tenant_factory()
    theirs = await added(stranger, provider="openai", api_key=OPENAI_KEY)

    deleted = await stranger.client.delete(credentials_path(stranger.organisation_id, theirs["id"]))

    assert deleted.status_code == 204
