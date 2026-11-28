# 01: Prefactor: one Job publisher port

**Ticket:** `21-01` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** Every background job is sent through one port, so a failed send no longer fails the request that queued it and tests can lose or hold a message. Nothing a Member sees changes.

**Blocked by:**
- None

**Status:** done

- [x] A Job publisher port with one operation per job the application queues today (ingestion, object deletion, Evaluation Run, Live Verdict, Suggestion run, Re-embed, Project deletion, the worker health probe); nothing else sends to Celery
- [x] The production adapter sends to Celery exactly as today; the fake records what was sent and can be told to lose or hold the next message, and to release held ones
- [x] A send that fails is logged with the job and its identifier and does not fail the request: the row is already committed and is the record (ADR-0020). The health probe is the exception and still reports the failure
- [x] Jobs that queue follow-on work from inside a task (automatic retries, object deletions after ingestion) go through the same port
- [x] Every job except the health probe ignores its result, so the API no longer subscribes to replies nobody reads
- [x] The publisher fake is listed with the other ports in the shared test seams
- [x] Existing behaviour is unchanged: the whole suite passes with no test rewritten to expect something different
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seams: the API seam and the task seam, with the Job publisher fake (`jobs` fixture), as the [shared test seams](../../specs/README.md#shared-test-seams) name them. New tests: `backend/tests/integration/test_job_publisher.py`.

1. **One port, one operation per job.** `app/worker/publisher.py`: `JobPublisher` with `ingest_document`, `delete_objects`, `run_evaluation`, `judge_live_verdict`, `run_suggestion`, `re_embed`, `delete_project` and `probe_worker`. Every `enqueue_*` helper and the health endpoint call `current_publisher()`; `grep -rn "\.delay(\|apply_async" backend/app` finds only `CeleryJobPublisher`.
2. **Adapters.** `CeleryJobPublisher` calls the registered task's `apply_async` with the same arguments, kwargs and countdown as before. `tests/fakes/jobs.py` `RecordingJobPublisher` records `sent`, and `lose_next()`, `hold_next()` / `release_held()` and `fail_next()`; tests `test_a_lost_job_leaves_its_row_as_committed` and `test_a_held_job_runs_once_released`.
3. **A failed send doesn't fail the request.** `test_a_send_that_fails_does_not_fail_the_upload_and_is_logged`: the confirm answers 201, the Document stays Queued, and the error log carries `job` (`documents.ingest`) and `job_id` (the Document's ID). The health probe still reports: `test_a_worker_health_probe_that_cannot_be_sent_is_reported` (503).
4. **Follow-on work from tasks.** `test_an_automatic_retry_is_sent_through_the_publisher` (attempt 2 with a countdown) and `test_object_deletions_after_ingestion_are_sent_through_the_publisher`; the Re-embed retry also goes through `current_publisher().re_embed`.
5. **Results ignored.** The tasks are declared `ignore_result=True` and the adapter sends with `ignore_result=True`; `test_every_job_but_the_health_probe_ignores_its_result` reads the messages off the Redis broker: `ignore_result` is true for every job and false for `worker.health_check`.
6. **Shared test seams.** The Job publisher row in `docs/specs/README.md` names the fake, its release of held messages and the `jobs` fixture.
7. **Behaviour unchanged.** No existing test was edited; `enqueue_*` keep their names and signatures. Locally the whole backend suite passes except 22 tests that fail identically on the base commit `0e77d83` because of the sandbox (see Gaps).
8. **Coverage.** `app/worker/publisher.py` and every changed `tasks.py` are at 100% line and branch coverage. The new branch in `app/api/health.py` is covered too. The memory limit stopped a full coverage run in the sandbox, so CI's gate has the final say.
9. **Glossary and ADRs.** No new domain term: the Job publisher is a technical port already named by the spec, and nothing a Member sees changes. ADR-0020 is unchanged; this ticket applies it. `docs/development.md` gains a "Background jobs" section.

## Gaps and best guesses

- **Best guess:** a health probe that can't be sent answers 503 `{"status": "error"}` (the endpoint's documented failure) rather than a 500.
- **Best guess:** in eager mode (tests) a send runs the task, so an error raised inside an eagerly run task is now logged by the publisher instead of propagating to the request. No existing test relied on that propagation.
- **Best guess:** the fake's lose and hold apply to jobs, not to the health probe; `fail_next` applies to both.
- **Local run:** the sandbox has no Docker. The suite ran against a local PostgreSQL 16 with pgvector 0.7.4 (a conda-forge build) and a local Redis, not the compose images (pgvector 0.8.1, RustFS). 22 tests fail the same way on the base commit: 12 because pgvector 0.7 lacks `hnsw.iterative_scan` (`test_embedding_models`, `test_re_embedding`, `test_retrieval_probe_index`) and 10 because RustFS is not running (`test_object_store`). Ruff, ruff format, mypy and `make link-check` pass.
