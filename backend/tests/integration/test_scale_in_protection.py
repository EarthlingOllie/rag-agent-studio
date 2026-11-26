"""Task seam for Scale-in protection (spec 22 stories 22 and 23, ADR-0021): a worker protects its
ECS task from scale-in from when a job takes its claim until the job ends, renewing the
protection with each heartbeat, and clears it when the job finishes, fails or is abandoned. A
failure to set or clear protection never fails the job.

The Scale-in protection fake records the calls; the jobs run eagerly through the API action that
queues them, and outcomes are read through the API."""

import asyncio
import logging
from datetime import timedelta

import pytest
from fastapi import FastAPI

from app.jobs.tasks import sweep_jobs
from tests.conftest import SignedUpMember
from tests.documents import chunks, create_project, documents, upload
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.fakes.protection import RecordingProtection
from tests.integration.test_evaluation import add_case
from tests.integration.test_evaluation_sides import start
from tests.integration.test_interrupted_evaluation_runs import Models
from tests.integration.test_interrupted_ingestion import held_converter, upload_in_background
from tests.integration.test_playground import ready_agent, three_tokens
from tests.jobs import settle_jobs_in_flight

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."


@pytest.fixture(autouse=True)
async def no_jobs_left_by_earlier_tests(app: FastAPI) -> None:
    """Earlier tests on this worker may have left jobs in flight, which a sweep here would
    recover too."""
    await settle_jobs_in_flight(app)


async def status_of(owner: SignedUpMember, project_id: str) -> str:
    (document,) = await documents(owner, project_id)
    status: str = document["status"]
    return status


async def test_an_ingestion_protects_its_task_until_it_finishes(
    app: FastAPI, owner: SignedUpMember, protection: RecordingProtection
) -> None:
    project_id = await create_project(owner)

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    assert await status_of(owner, project_id) == "ready"
    (holder,) = protection.holders()
    assert protection.calls_for(holder) == ["protect", "release"]


async def test_protection_is_renewed_with_each_heartbeat_while_the_job_runs(
    app: FastAPI,
    owner: SignedUpMember,
    protection: RecordingProtection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "0.05")
    converter = held_converter(app, monkeypatch)
    project_id = await create_project(owner)
    running = await upload_in_background(app, owner, project_id)
    await converter.wait_until_started()

    # A few heartbeats go by (in real time) while conversion is held.
    await asyncio.sleep(0.5)
    renewed = protection.steps()
    converter.release.set()
    await running

    assert renewed == ["protect", "renew"]
    assert protection.steps() == ["protect", "renew", "release"]
    assert protection.calls_for(protection.holders()[0]).count("renew") >= 3


async def test_a_job_that_fails_releases_its_protection(
    app: FastAPI, owner: SignedUpMember, protection: RecordingProtection
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    assert await status_of(owner, project_id) == "failed"
    (holder,) = protection.holders()
    assert protection.calls_for(holder) == ["protect", "release"]


async def test_a_copy_given_up_for_dead_releases_its_protection_when_it_stops(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    protection: RecordingProtection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first copy stalls and is restarted; the restarted copy protects and releases under its
    own claim, and the abandoned copy, when it wakes and finds its claim gone, releases too."""
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "3600")
    converter = held_converter(app, monkeypatch)
    project_id = await create_project(owner)
    first = await upload_in_background(app, owner, project_id)
    await converter.wait_until_started()
    clock.advance(timedelta(minutes=6))
    swept = await asyncio.to_thread(sweep_jobs.apply, kwargs={"at": clock.now().isoformat()})
    assert swept.get(disable_sync_subtasks=False) == 1
    abandoned, restarted = protection.holders()
    assert protection.calls_for(restarted) == ["protect", "release"]
    assert protection.calls_for(abandoned) == ["protect"]

    converter.release.set()
    await first

    assert protection.calls_for(abandoned) == ["protect", "release"]
    assert await status_of(owner, project_id) == "ready"


async def test_an_evaluation_run_protects_its_task_until_it_completes(
    app: FastAPI, owner: SignedUpMember, protection: RecordingProtection
) -> None:
    Models(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    before = len(protection.holders())  # The Agent's Documents were ingested.

    started = await start(owner, project_id, agent_id)

    assert started.status_code == 202, started.text
    assert started.json()["status"] == "completed"
    (holder,) = protection.holders()[before:]
    assert protection.calls_for(holder) == ["protect", "release"]


@pytest.mark.parametrize("step", ["protect", "renew", "release"])
async def test_a_failure_to_set_or_clear_protection_is_logged_and_the_job_goes_on(
    app: FastAPI,
    owner: SignedUpMember,
    protection: RecordingProtection,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    step: str,
) -> None:
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "0.05")
    converter = held_converter(app, monkeypatch)
    protection.fail(step)
    project_id = await create_project(owner)

    with caplog.at_level(logging.WARNING, logger="app.jobs.reliability"):
        running = await upload_in_background(app, owner, project_id)
        await converter.wait_until_started()
        await asyncio.sleep(0.2)
        converter.release.set()
        document = await running

    assert await status_of(owner, project_id) == "ready"
    assert len(await chunks(owner, project_id, document["id"])) == 1
    (holder,) = protection.holders()
    assert protection.calls_for(holder)[-1] == "release"
    message = f"Scale-in protection failed to {step}"
    warnings = [r for r in caplog.records if r.getMessage() == message]
    assert warnings
    assert all(
        getattr(r, "claim_id", None) == str(holder) and r.exc_info is not None for r in warnings
    )
