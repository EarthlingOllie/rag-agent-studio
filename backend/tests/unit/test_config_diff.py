"""The diff of two AgentConfigs, through its interface: a structural diff of every field, by
dotted path, with the items added and removed for lists and a line diff for markdown."""

import uuid

from pydantic import JsonValue

from app.agents.config import AgentConfig
from app.versioning.diff import FieldChange, Line, diff_configs, diff_text

CREDENTIAL = uuid.UUID("11111111-1111-1111-1111-111111111111")
TAG_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TAG_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def config(**groups: object) -> AgentConfig:
    return AgentConfig.model_validate(groups)


def test_identical_configs_have_no_changes() -> None:
    assert diff_configs(AgentConfig(), AgentConfig()) == []


def test_a_changed_scalar_in_a_nested_group_is_reported_by_its_path() -> None:
    before = config(behaviour={"temperature": 0.7}, experience={"ui_text": {"send_button": "Go"}})
    after = config(behaviour={"temperature": 0.2}, experience={"ui_text": {"send_button": None}})

    assert diff_configs(before, after) == [
        FieldChange("behaviour.temperature", 0.7, 0.2),
        FieldChange("experience.ui_text.send_button", "Go", None),
    ]


def test_a_model_choice_set_or_cleared_is_one_change_of_the_whole_choice() -> None:
    choice: JsonValue = {"credential_id": str(CREDENTIAL), "model": "gpt-4.1-mini"}
    before = config()
    after = config(behaviour={"model": choice})

    assert diff_configs(before, after) == [FieldChange("behaviour.model", None, choice)]
    assert diff_configs(after, before) == [FieldChange("behaviour.model", choice, None)]


def test_a_changed_model_inside_a_choice_is_reported_by_its_own_path() -> None:
    before = config(retrieval={"reranker": {"credential_id": str(CREDENTIAL), "model": "a"}})
    after = config(retrieval={"reranker": {"credential_id": str(CREDENTIAL), "model": "b"}})

    assert diff_configs(before, after) == [FieldChange("retrieval.reranker.model", "a", "b")]


def test_lists_report_the_items_added_and_removed() -> None:
    before = config(
        retrieval={"tag_ids": [str(TAG_A)]},
        experience={"starter_questions": ["How many days off?", "Who do I ask?"]},
    )
    after = config(
        retrieval={"tag_ids": [str(TAG_A), str(TAG_B)]},
        experience={"starter_questions": ["Who do I ask?", "Where is the handbook?"]},
    )

    assert diff_configs(before, after) == [
        FieldChange(
            "retrieval.tag_ids",
            [str(TAG_A)],
            [str(TAG_A), str(TAG_B)],
            added=[str(TAG_B)],
            removed=[],
        ),
        FieldChange(
            "experience.starter_questions",
            ["How many days off?", "Who do I ask?"],
            ["Who do I ask?", "Where is the handbook?"],
            added=["Where is the handbook?"],
            removed=["How many days off?"],
        ),
    ]


def test_a_reordered_list_is_a_change_with_nothing_added_or_removed() -> None:
    before = config(experience={"starter_questions": ["One?", "Two?"]})
    after = config(experience={"starter_questions": ["Two?", "One?"]})

    assert diff_configs(before, after) == [
        FieldChange(
            "experience.starter_questions",
            ["One?", "Two?"],
            ["Two?", "One?"],
            added=[],
            removed=[],
        )
    ]


def test_the_markdown_system_prompt_also_gets_a_line_diff() -> None:
    before = config(behaviour={"system_prompt": "# Role\nYou help with HR.\nBe brief."})
    after = config(behaviour={"system_prompt": "# Role\nYou help with HR and IT.\nBe brief."})

    assert diff_configs(before, after) == [
        FieldChange(
            "behaviour.system_prompt",
            "# Role\nYou help with HR.\nBe brief.",
            "# Role\nYou help with HR and IT.\nBe brief.",
            lines=[
                Line("equal", "# Role"),
                Line("delete", "You help with HR."),
                Line("insert", "You help with HR and IT."),
                Line("equal", "Be brief."),
            ],
        )
    ]


def test_plain_text_fields_get_no_line_diff() -> None:
    before = config(behaviour={"fallback_text": "No idea."})
    after = config(behaviour={"fallback_text": "I don't know."})

    assert diff_configs(before, after) == [
        FieldChange("behaviour.fallback_text", "No idea.", "I don't know.")
    ]


def test_changes_follow_the_config_order_across_every_group() -> None:
    before = AgentConfig()
    after = config(
        guardrails={"fail_mode": "open"},
        behaviour={"max_output_tokens": 100},
        experience={"greeting": "Hi"},
        retrieval={"top_k": 3},
    )

    assert [change.path for change in diff_configs(before, after)] == [
        "behaviour.max_output_tokens",
        "retrieval.top_k",
        "experience.greeting",
        "guardrails.fail_mode",
    ]


def test_a_text_diff_of_added_and_removed_text() -> None:
    assert diff_text("", "One\nTwo") == [Line("insert", "One"), Line("insert", "Two")]
    assert diff_text("One\nTwo", "") == [Line("delete", "One"), Line("delete", "Two")]
    assert diff_text("Same", "Same") == [Line("equal", "Same")]
    assert diff_text("a\nb\nc", "a\nB\nc\nd") == [
        Line("equal", "a"),
        Line("delete", "b"),
        Line("insert", "B"),
        Line("equal", "c"),
        Line("insert", "d"),
    ]
