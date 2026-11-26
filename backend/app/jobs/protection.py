"""Scale-in protection (spec 22, ADR-0021): the port a worker protects its ECS task through while
it holds a job, so scaling in, or a deploy, never stops a task in the middle of one.

The job reliability module calls it (``app.jobs.reliability.heartbeat``): ``protect`` when a job
has taken its claim, ``renew`` with each heartbeat, and ``release`` when the job ends, however it
ends. Each call names the claim it is for, since a task runs several jobs at once
(``--concurrency``) and ECS protects the task as a whole.

- **ECS** (``EcsTaskProtection``): calls the ECS agent's task-protection endpoint
  (``$ECS_AGENT_URI/task-protection/v1/state``), which acts on the calling task only. Protection
  carries an expiry ``expires_in_minutes`` ahead, so a task whose worker died is protected for a
  few minutes at most. Each job holding protection keeps a file under ``holders_dir`` (the
  task's own ``/tmp``, shared by its worker processes), touched as it renews; a release clears
  the task's protection only when no other job's file is younger than the expiry.
- **None** (``NoProtection``): where there is no ECS (locally), every call does nothing.

Tests install a fake that records the calls (``tests.fakes.protection``).
"""

import abc
import os
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

from app.core.settings import Settings


class ScaleInProtection(abc.ABC):
    """The port. A call that fails raises; the reliability module logs it and the job goes on."""

    @abc.abstractmethod
    async def protect(self, holder: uuid.UUID) -> None:
        """The job with this claim has started: protect the task."""

    @abc.abstractmethod
    async def renew(self, holder: uuid.UUID) -> None:
        """The job is still running: push the protection's expiry forward."""

    @abc.abstractmethod
    async def release(self, holder: uuid.UUID) -> None:
        """The job has ended: the task needs no protection for it any more."""


class NoProtection(ScaleInProtection):
    """Outside ECS there is no scale-in to protect from."""

    async def protect(self, holder: uuid.UUID) -> None:
        return None

    async def renew(self, holder: uuid.UUID) -> None:
        return None

    async def release(self, holder: uuid.UUID) -> None:
        return None


class ProtectionRefusedError(Exception):
    """The ECS agent did not set or clear protection."""


class EcsTaskProtection(ScaleInProtection):
    """Sets and clears the task's scale-in protection through the ECS agent."""

    def __init__(
        self,
        agent_uri: str,
        expires_in_minutes: int,
        holders_dir: Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._url = f"{agent_uri.rstrip('/')}/task-protection/v1/state"
        self._expires_in_minutes = expires_in_minutes
        self._holders_dir = holders_dir
        self._transport = transport
        self._now = now

    async def protect(self, holder: uuid.UUID) -> None:
        self._hold(holder)
        await self._put({"ProtectionEnabled": True, "ExpiresInMinutes": self._expires_in_minutes})

    async def renew(self, holder: uuid.UUID) -> None:
        await self.protect(holder)

    async def release(self, holder: uuid.UUID) -> None:
        self._holder(holder).unlink(missing_ok=True)
        if not self._others_hold():
            await self._put({"ProtectionEnabled": False})

    def _holder(self, holder: uuid.UUID) -> Path:
        return self._holders_dir / str(holder)

    def _hold(self, holder: uuid.UUID) -> None:
        self._holders_dir.mkdir(parents=True, exist_ok=True)
        now = self._now()
        path = self._holder(holder)
        path.touch()
        # The holder's time comes from the adapter's clock, which ages it in ``_others_hold``.
        os.utime(path, (now, now))

    def _others_hold(self) -> bool:
        """Whether another job in this task holds protection: its file was touched within the
        expiry. An older file belongs to a job whose worker process died without releasing."""
        if not self._holders_dir.is_dir():
            return False
        oldest = self._now() - self._expires_in_minutes * 60
        return any(path.stat().st_mtime > oldest for path in self._holders_dir.iterdir())

    async def _put(self, body: dict[str, object]) -> None:
        async with httpx.AsyncClient(transport=self._transport, timeout=10) as client:
            response = await client.put(self._url, json=body)
        answer = response.json() if response.content else {}
        if response.status_code != 200 or "failure" in answer or "error" in answer:
            raise ProtectionRefusedError(f"{response.status_code}: {response.text}")


def build_protection(settings: Settings) -> ScaleInProtection:
    """ECS task protection where the ECS agent is there (ECS sets ``ECS_AGENT_URI`` in every
    container); no protection elsewhere."""
    if settings.ecs_agent_uri is None:
        return NoProtection()
    return EcsTaskProtection(
        settings.ecs_agent_uri,
        settings.scale_in_protection_minutes,
        Path(tempfile.gettempdir()) / "scale-in-protection",
    )


_installed: list[ScaleInProtection] = [NoProtection()]


def install_protection(protection: ScaleInProtection) -> None:
    """The worker installs the adapter its settings choose as it starts; tests install the fake."""
    _installed[:] = [protection]


def current_protection() -> ScaleInProtection:
    return _installed[0]
