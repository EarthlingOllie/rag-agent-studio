"""Streams that outlast whoever is reading them.

``outlasting`` passes a source's items on as they come, but runs the source in its own task: if
the reader stops (an HTTP client hangs up and the response is cancelled), the source still runs
to its end. A Call's turn needs this: the voice layer stops reading a reply the Visitor talked
over, and the Agent still finishes it, so the reply is saved with its whole text.
"""

import asyncio
from collections.abc import AsyncIterator

# The sources still running, kept so they aren't collected while no reader holds them.
_running: set[asyncio.Task[None]] = set()


async def outlasting[T](source: AsyncIterator[T]) -> AsyncIterator[T]:
    """Yields ``source``'s items; ``source`` runs to its end even if this stops being read.
    An error in ``source`` is raised here while it is still read; once nobody reads, asyncio
    reports it as a task's unretrieved exception."""
    items: asyncio.Queue[tuple[T] | None] = asyncio.Queue()

    async def run() -> None:
        try:
            async for item in source:
                items.put_nowait((item,))
        finally:
            items.put_nowait(None)

    task = asyncio.create_task(run())
    _running.add(task)
    task.add_done_callback(_running.discard)
    while (item := await items.get()) is not None:
        yield item[0]
    await task
