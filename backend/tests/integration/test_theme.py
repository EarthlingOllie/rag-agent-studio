"""API seam: the Organisation's Theme. Owners edit it, every Member views it, changes are audited.

Everything is observed through the API: the Theme endpoints, the font allowlist and Audit
Events from the Audit list endpoint.
"""

import asyncio
import copy
from datetime import timedelta
from typing import Any

import pytest

from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock

DEFAULT_THEME: dict[str, Any] = {
    "colours": {
        "primary": {"light": "#4f46e5", "dark": "#818cf8"},
        "on_primary": {"light": "#ffffff", "dark": "#111827"},
        "surface": {"light": "#ffffff", "dark": "#111827"},
        "on_surface": {"light": "#111827", "dark": "#f9fafb"},
        "accent": {"light": "#0f766e", "dark": "#2dd4bf"},
        "muted": {"light": "#4b5563", "dark": "#9ca3af"},
    },
    "radius": 12,
    "font": "Inter",
    "mode": "light",
    "launcher_type": "bubble",
    "launcher_position": "bottom-right",
}


def theme_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/theme"


def a_theme(**changes: Any) -> dict[str, Any]:
    theme = copy.deepcopy(DEFAULT_THEME)
    theme.update(changes)
    return theme


def with_colour(token: str, light: str, dark: str) -> dict[str, Any]:
    theme = a_theme()
    theme["colours"][token] = {"light": light, "dark": dark}
    return theme


async def theme_of(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.get(theme_path(member.organisation_id))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def without_updated_at(theme: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in theme.items() if key != "updated_at"}


async def theme_events(owner: SignedUpMember) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "theme.updated"},
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# Reading


async def test_a_new_organisation_has_the_default_theme(owner: SignedUpMember) -> None:
    theme = await theme_of(owner)

    assert without_updated_at(theme) == DEFAULT_THEME
    assert theme["updated_at"] is None


async def test_the_font_allowlist_is_a_curated_list_of_google_fonts(owner: SignedUpMember) -> None:
    response = await owner.client.get("/api/themes/fonts")

    assert response.status_code == 200
    fonts = response.json()
    families = [font["family"] for font in fonts]
    assert families[0] == "Inter"
    assert {"Inter", "Roboto", "Merriweather"} <= set(families)
    assert len(families) == len(set(families))
    assert all(font["category"] in {"sans-serif", "serif", "monospace"} for font in fonts)


# Owners edit


async def test_owners_save_every_part_of_the_theme_and_it_applies_at_once(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    new_theme: dict[str, Any] = {
        "colours": {
            "primary": {"light": "#B91C1C", "dark": "#F87171"},
            "on_primary": {"light": "#ffffff", "dark": "#1f2937"},
            "surface": {"light": "#fafaf9", "dark": "#1c1917"},
            "on_surface": {"light": "#1c1917", "dark": "#fafaf9"},
            "accent": {"light": "#b45309", "dark": "#fbbf24"},
            "muted": {"light": "#57534e", "dark": "#a8a29e"},
        },
        "radius": 4,
        "font": "Merriweather",
        "mode": "auto",
        "launcher_type": "bubble",
        "launcher_position": "bottom-left",
    }

    saved = await owner.client.put(theme_path(owner.organisation_id), json=new_theme)

    assert saved.status_code == 200, saved.text
    expected = copy.deepcopy(new_theme)
    # Colours are stored in lower case.
    expected["colours"]["primary"] = {"light": "#b91c1c", "dark": "#f87171"}
    assert without_updated_at(saved.json()) == expected
    assert saved.json()["updated_at"] == clock.now().isoformat().replace("+00:00", "Z")
    # No publishing step: the next read sees the change.
    assert await theme_of(owner) == saved.json()


async def test_the_launcher_can_be_an_inline_container(owner: SignedUpMember) -> None:
    saved = await owner.client.put(
        theme_path(owner.organisation_id), json=a_theme(launcher_type="inline", mode="dark")
    )

    assert saved.status_code == 200, saved.text
    assert (await theme_of(owner))["launcher_type"] == "inline"
    assert (await theme_of(owner))["mode"] == "dark"


async def test_saving_again_replaces_the_theme(owner: SignedUpMember) -> None:
    path = theme_path(owner.organisation_id)
    assert (await owner.client.put(path, json=a_theme(radius=0))).status_code == 200

    second = await owner.client.put(path, json=a_theme(radius=24, font="Roboto"))

    assert second.status_code == 200
    theme = await theme_of(owner)
    assert (theme["radius"], theme["font"]) == (24, "Roboto")


@pytest.mark.parametrize(
    ("change", "location"),
    [
        (with_colour("primary", "red", "#000000"), ["body", "colours", "primary", "light"]),
        (with_colour("muted", "#000000", "#12345"), ["body", "colours", "muted", "dark"]),
        (with_colour("accent", "#00000g", "#000000"), ["body", "colours", "accent", "light"]),
        (a_theme(radius=-1), ["body", "radius"]),
        (a_theme(radius=25), ["body", "radius"]),
        (a_theme(font="Comic Sans MS"), ["body", "font"]),
        (a_theme(mode="sepia"), ["body", "mode"]),
        (a_theme(launcher_type="popup"), ["body", "launcher_type"]),
        (a_theme(launcher_position="top-left"), ["body", "launcher_position"]),
    ],
    ids=[
        "colour name",
        "short hex",
        "not hex",
        "negative radius",
        "radius too large",
        "font off the allowlist",
        "unknown mode",
        "unknown launcher",
        "unknown position",
    ],
)
async def test_invalid_themes_are_refused_and_change_nothing(
    owner: SignedUpMember, change: dict[str, Any], location: list[str]
) -> None:
    response = await owner.client.put(theme_path(owner.organisation_id), json=change)

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [location]
    assert without_updated_at(await theme_of(owner)) == DEFAULT_THEME
    assert await theme_events(owner) == []


async def test_a_theme_must_name_every_colour_token(owner: SignedUpMember) -> None:
    theme = a_theme()
    del theme["colours"]["accent"]

    response = await owner.client.put(theme_path(owner.organisation_id), json=theme)

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [["body", "colours", "accent"]]


async def test_colours_that_fail_contrast_are_saved_because_contrast_only_warns(
    owner: SignedUpMember,
) -> None:
    # Pale grey text on white is about 1.1:1, far below WCAG AA; the Studio warns, the API saves.
    unreadable = with_colour("on_surface", "#eeeeee", "#111111")
    unreadable["colours"]["surface"] = {"light": "#ffffff", "dark": "#121212"}

    response = await owner.client.put(theme_path(owner.organisation_id), json=unreadable)

    assert response.status_code == 200, response.text
    assert (await theme_of(owner))["colours"]["on_surface"]["light"] == "#eeeeee"


# Editors view


async def test_editors_view_the_theme_but_cannot_change_it(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    assert (
        await owner.client.put(theme_path(owner.organisation_id), json=a_theme(radius=2))
    ).status_code == 200
    editor = await member_factory(owner, "editor")

    viewed = await theme_of(editor)
    refused = await editor.client.put(theme_path(owner.organisation_id), json=a_theme(radius=20))

    assert viewed == await theme_of(owner)
    assert viewed["radius"] == 2
    assert (refused.status_code, refused.json()) == (403, {"detail": "Only Owners can do this"})
    assert (await theme_of(owner))["radius"] == 2
    assert len(await theme_events(owner)) == 1


async def test_each_organisation_has_its_own_theme(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()

    await owner.client.put(theme_path(owner.organisation_id), json=a_theme(font="Lora"))

    assert (await theme_of(owner))["font"] == "Lora"
    assert without_updated_at(await theme_of(other)) == DEFAULT_THEME


# Audit


async def test_theme_changes_are_audit_events_with_what_changed(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    path = theme_path(owner.organisation_id)
    first = with_colour("primary", "#b91c1c", "#f87171")
    first["radius"] = 6
    await owner.client.put(path, json=first)
    first_at = clock.now()
    clock.advance(timedelta(minutes=1))
    second = copy.deepcopy(first)
    second["mode"] = "auto"
    await owner.client.put(path, json=second)

    events = await theme_events(owner)

    assert [(e["actor"]["id"], e["target"]["type"], e["before"], e["after"]) for e in events] == [
        (owner.member_id, "theme", {"mode": "light"}, {"mode": "auto"}),
        (
            owner.member_id,
            "theme",
            {"colours": {"primary": DEFAULT_THEME["colours"]["primary"]}, "radius": 12},
            {"colours": {"primary": {"light": "#b91c1c", "dark": "#f87171"}}, "radius": 6},
        ),
    ]
    assert events[1]["occurred_at"] == first_at.isoformat().replace("+00:00", "Z")
    assert events[0]["target"]["id"] == events[1]["target"]["id"] is not None


async def test_saving_the_same_theme_records_nothing(owner: SignedUpMember) -> None:
    path = theme_path(owner.organisation_id)

    unchanged = await owner.client.put(path, json=a_theme())

    assert unchanged.status_code == 200
    assert await theme_events(owner) == []
    # The default stays the default: nothing was stored.
    assert unchanged.json()["updated_at"] is None


async def test_owners_saving_at_once_both_succeed_and_one_theme_wins(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    co_owner = await member_factory(owner, "owner")
    path = theme_path(owner.organisation_id)

    answers = await asyncio.gather(
        owner.client.put(path, json=a_theme(radius=1)),
        co_owner.client.put(path, json=a_theme(radius=2)),
    )

    assert [answer.status_code for answer in answers] == [200, 200]
    assert (await theme_of(owner))["radius"] in {1, 2}
    assert len(await theme_events(owner)) == 2
