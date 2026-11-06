"""The canary stream filter and the post-completion check, through their interfaces.

The filter is fed an answer in chunks, as a model streams it. Table-driven chunkings put the
canary at the start, middle and end of the answer and split it at every position; near misses
must stream through untouched."""

import base64
import textwrap

import pytest

from app.guardrails.canary import CanaryFilter, encoded_leak, new_canary

CANARY = "3f9a1c7e5b2d8046af1e"


def run(chunks: list[str], canary: str = CANARY) -> tuple[str, bool]:
    """Feeds the chunks; returns everything released and whether a leak was caught."""
    canary_filter = CanaryFilter(canary)
    released = ""
    for chunk in chunks:
        released += canary_filter.feed(chunk)
        if canary_filter.leaked:
            return released, True
    return released + canary_filter.finish(), False


def test_a_new_canary_is_random_and_as_long_as_the_filter_expects() -> None:
    canaries = {new_canary() for _ in range(50)}
    assert len(canaries) == 50
    assert all(len(c) == 20 and c.isalnum() and c == c.lower() for c in canaries)


def splits(text: str) -> list[list[str]]:
    """Every way of cutting ``text`` into two chunks, and into one chunk per character."""
    return [[text[:at], text[at:]] for at in range(len(text) + 1)] + [list(text)]


# (text before the canary, the canary as written, text after it)
PLACES = {
    "start": ("", CANARY, " is my secret."),
    "middle": ("My secret is ", CANARY, ", keep it."),
    "end": ("My secret is ", CANARY, ""),
    "alone": ("", CANARY, ""),
    "after a long answer": ("Annual leave is 25 days for everyone. The secret: ", CANARY, "."),
    "upper case": ("My secret is ", CANARY.upper(), "."),
    "spaced": ("My secret is ", " ".join(CANARY), "."),
    "line broken": ("My secret is ", f"{CANARY[:7]}\n{CANARY[7:]}", "."),
}


@pytest.mark.parametrize("place", PLACES)
def test_a_leak_is_caught_wherever_it_is_and_however_it_is_split(place: str) -> None:
    before, leak, after = PLACES[place]
    answer = before + leak + after
    for chunks in splits(answer):
        released, leaked = run(chunks)
        assert leaked, chunks
        # Only text before the canary was let through: no fragment of it, not even one character.
        assert before.startswith(released), chunks


@pytest.mark.parametrize("at", range(len(CANARY) + 1))
def test_a_canary_split_at_every_position_across_three_chunks_is_caught(at: int) -> None:
    for second in range(at, len(CANARY) + 1):
        chunks = ["Here: ", CANARY[:at], CANARY[at:second], CANARY[second:], " done."]
        released, leaked = run(chunks)
        assert leaked
        assert "Here: ".startswith(released)


NEAR_MISSES = {
    "one character wrong": CANARY[:-1] + "0",
    "missing its last character": CANARY[:-1],
    "missing its first character": CANARY[1:],
    "two halves apart": f"{CANARY[:10]} and then {CANARY[10:]}",
    "joined by a hyphen": f"{CANARY[:10]}-{CANARY[10:]}",
    "another hex string": "0123456789abcdef0123",
    "empty": "",
    "short": "Hi",
}


@pytest.mark.parametrize("miss", NEAR_MISSES)
def test_near_misses_stream_through_unchanged(miss: str) -> None:
    answer = f"Leave is 25 days. {NEAR_MISSES[miss]} Ask HR."
    for chunks in splits(answer):
        assert run(chunks) == (answer, False), chunks


def test_text_is_held_back_only_while_it_could_still_be_the_start_of_a_canary() -> None:
    canary_filter = CanaryFilter(CANARY)
    answer = "Annual leave is twenty five days for everyone, in every team."
    # A buffer as long as the canary is held back (counting letters, not spaces) ...
    released = canary_filter.feed(answer)
    held = answer[len(released) :]
    assert len(held.replace(" ", "")) == len(CANARY)
    assert released + held == answer
    # ... and released when the answer ends.
    assert canary_filter.finish() == held
    assert canary_filter.finish() == ""


def test_once_a_leak_is_caught_nothing_more_is_released() -> None:
    canary_filter = CanaryFilter(CANARY)
    canary_filter.feed(f"Secret: {CANARY}")
    assert canary_filter.leaked
    assert canary_filter.feed("more text " * 10) == ""
    assert canary_filter.finish() == ""


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


ENCODED = {
    "base64": b64(CANARY),
    "base64 inside a sentence's base64": b64(f"The secret is {CANARY}, ok"),
    "base64 one byte in": b64(f"x{CANARY}"),
    "base64 two bytes in": b64(f"xy{CANARY}"),
    "base64 of the upper-case canary": b64(CANARY.upper()),
    "base64 wrapped over lines": "\n".join(textwrap.wrap(b64(f"Secret {CANARY}"), 8)),
    "base64 straight after a word": "Secret" + b64(f"z{CANARY}"),
    "separated by hyphens": "-".join(CANARY),
    "separated by dots": ".".join(CANARY.upper()),
    "reversed": CANARY[::-1],
}


@pytest.mark.parametrize("encoding", ENCODED)
def test_the_post_completion_check_finds_encoded_leaks(encoding: str) -> None:
    text = f"Sure! {ENCODED[encoding]} Hope that helps."
    assert encoded_leak(text, CANARY) is not None


def test_the_post_completion_check_names_the_encoding() -> None:
    assert encoded_leak(b64(CANARY), CANARY) == "base64"
    assert encoded_leak("-".join(CANARY), CANARY) == "separated"
    assert encoded_leak(CANARY[::-1], CANARY) == "reversed"


@pytest.mark.parametrize("miss", NEAR_MISSES)
def test_the_post_completion_check_ignores_near_misses(miss: str) -> None:
    text = f"Leave is 25 days. {NEAR_MISSES[miss]} {b64(NEAR_MISSES[miss])} Ask HR."
    if miss == "joined by a hyphen":
        # Separators are stripped, so a hyphen-joined canary is a leak, not a near miss.
        assert encoded_leak(text, CANARY) == "separated"
    else:
        assert encoded_leak(text, CANARY) is None
