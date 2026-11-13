"""An answer's response gives back its reservation even when an anyio cancel scope ends it.

anyio's cancel scopes cancel level-triggered: every await inside a cancelled scope is cancelled
again, so a release that awaits Redis in the response's ``finally`` would itself be cancelled
and the Agent's place in flight kept until its lease lapses. The release is shielded so it
completes."""

from collections.abc import AsyncIterator, MutableMapping
from typing import Any

import anyio
import anyio.lowlevel

from app.embed.admission import RENEW_SECONDS, Admission, HeldStream, Reservation


class RecordingAdmission(Admission):
    """An admission whose release awaits (as the round trip to Redis does) before it counts."""

    def __init__(self) -> None:
        self.released: list[Reservation] = []

    async def hold(self, reservation: Reservation, every: float = RENEW_SECONDS) -> None:
        await anyio.sleep_forever()

    async def release(self, reservation: Reservation) -> None:
        await anyio.lowlevel.checkpoint()
        self.released.append(reservation)


async def test_a_response_its_cancel_scope_ends_still_gives_back_its_reservation() -> None:
    admission = RecordingAdmission()
    reservation = Reservation(key="reserved:agent", member="reply")
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        await anyio.sleep_forever()
        raise AssertionError("unreachable")  # pragma: no cover

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    with anyio.CancelScope() as scope:

        async def events() -> AsyncIterator[str]:
            yield "data: one\n\n"
            scope.cancel()
            await anyio.sleep_forever()
            yield "data: never\n\n"  # pragma: no cover

        response = HeldStream(events(), admission, reservation)
        await response(
            {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}}, receive, send
        )

    assert scope.cancelled_caught
    assert sent[0]["type"] == "http.response.start"
    assert admission.released == [reservation]
