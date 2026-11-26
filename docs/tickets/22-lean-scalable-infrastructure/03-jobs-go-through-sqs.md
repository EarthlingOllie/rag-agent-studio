# 03: Jobs go through SQS

**Ticket:** `22-03` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** Locally and on AWS, background jobs are sent through SQS and routed to the general or runs queue. `make dev` gains a Floci container for SQS, and every user journey still passes.

**Blocked by:**
- `21-01`
- `21-02`
- `21-03`
- `21-04`
- `21-05`
- `21-06`
- `21-07`
- `21-08`
- `21-09`
- `21-10`
- `21-11`
- `21-12`
- `22-02`

**Status:** done

- [x] The Job publisher's production adapter publishes to SQS: Evaluation Runs and Suggestion runs to the runs queue, every other job to the general queue
- [x] Celery uses predefined queues named by settings, so no task lists or creates queues; the queue names and the SQS endpoint override are settings validated at start-up, with no fallback to Redis as the broker
- [x] Redis still holds sessions, sign-in throttling, rate limits, Token Budgets and the health probe's reply
- [x] `make dev` starts a pinned Floci container used for SQS only, with storage kept between restarts; the API creates both queues at start-up when a setting says so; one local worker serves both queues
- [x] Automatic retries (at most five minutes) work on the SQS transport
- [x] Messages carry identifiers only
- [x] A task-seam test with the publisher fake asserts the queue each job type goes to
- [x] The test that starts a real worker runs against Floci's SQS, and CI's backend workflow has Floci as a service
- [x] The end-to-end suite passes on the Compose stack
- [x] The development guide lists the new service, its port and the queue settings
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seams: the task seam with the Job publisher fake, the real transport (Celery on Floci's SQS with a real worker), the API seam for startup and settings, and the end-to-end suite on the Compose stack ([shared test seams](../../specs/README.md#shared-test-seams)). Code: `backend/app/worker/celery_app.py`, `app/worker/publisher.py`, `app/worker/queues.py` (new), `app/core/settings.py`, `app/main.py`; `docker-compose.yml`, `Makefile`, `.github/workflows/backend.yml`, `.env.example`; tests in `backend/tests/sqs.py` (new), `tests/integration/test_job_queues.py` (new), `test_job_publisher.py`, `test_worker_entrypoint.py`, `test_worker_health.py`, `test_settings.py`, `test_logging.py`, `test_telemetry.py`, `tests/unit/test_aws_task_settings.py`.

1. **The production adapter publishes to SQS, runs to the runs queue.** `Job.queue` is `queue_for(task)`: `runs` for `evaluation.run` and `suggestions.run` (`RUNS_QUEUE_TASKS`), `general` for every other job. `CeleryJobPublisher.send` passes `queue=` the configured name, and Celery's broker is SQS. `test_job_publisher.py::test_each_job_lands_on_its_queue_carrying_identifiers_only` sends every job type through the real adapter to Floci and reads both queues with boto3: the two run jobs are on the runs queue and the six others on the general queue.
2. **Predefined queues named by settings, validated, no Redis broker.** `configure_celery` gives Celery both queues by URL (`broker_transport_options.predefined_queues`), `task_queues`, `task_default_queue` = general, `task_routes` for the run tasks and `task_create_missing_queues=False`; remote control is off (SQS has no broadcast). The broker URL is `sqs://` (plus Floci's static keys and endpoint locally). Settings: `GENERAL_QUEUE_NAME/URL`, `RUNS_QUEUE_NAME/URL` (required: a name SQS accepts, two different queues, each URL ending in its name), `SQS_ENDPOINT_URL`, `AWS_REGION`, `SQS_ACCESS_KEY_ID/SECRET_ACCESS_KEY`, `SQS_CREATE_QUEUES`. There is no broker setting at all, so nothing can fall back to Redis. `test_settings.py` (five new tests: a missing queue setting with Redis configured, a name SQS refuses, a URL of another queue, one queue named twice, a retry backoff over five minutes) and `test_worker_entrypoint.py::test_worker_entrypoint_points_celery_at_the_configured_queues_not_at_redis`, `test_scheduled_jobs_go_to_the_general_queue_and_runs_to_the_runs_queue` (Celery's router for everything Beat sends and for a task sent without a queue), `test_a_broker_on_aws_has_no_endpoint_or_keys`. `tests/unit/test_aws_task_settings.py::test_each_container_sends_jobs_to_the_terraform_queues_on_aws_sqs` loads each ECS container's recorded environment (`infra/modules/ecs/tests/task-settings.json`, unchanged: 22-02's names were kept) and gets AWS SQS through the task role (`sqs://`), region `eu-west-2`, no queue creation.
3. **Redis still holds sessions, throttling, rate limits, Token Budgets and the probe's reply.** Only the broker changed: `result_backend` stays `REDIS_URL` (asserted in the entrypoint test above), and the session, sign-in, widget rate-limit and Token Budget code and their suites are untouched and pass. `test_worker_health.py` gets the probe's reply back through Redis from a worker on SQS.
4. **`make dev` starts Floci; the API creates the queues; one worker.** Compose service `floci` (`floci/floci:2.5.0`, port 4566, `FLOCI_STORAGE_MODE=persistent` with the `floci-data` volume, `FLOCI_HOSTNAME=floci`) is used for SQS only (RustFS stays the object store). The backend containers get the queue settings with `SQS_CREATE_QUEUES=true`; the API's startup calls `create_queues` (one hour and twelve hours of visibility, as the queue module) and the worker and Beat wait for the API to be healthy. The one `worker` service runs without `-Q`. `test_job_queues.py::test_the_api_creates_both_queues_at_startup_when_told_to` (twice, so an existing queue is fine) and `test_the_api_creates_no_queue_unless_told_to`; `test_worker_entrypoint.py::test_one_worker_serves_both_queues`.
5. **Automatic retries, at most five minutes, on SQS.** `INGESTION_RETRY_MAX_SECONDS` is capped at 300 (`le=300`); a retry is a message with a countdown that the receiving worker holds until it is due, inside the queues' visibility timeouts. `test_job_queues.py::test_an_automatic_retry_gets_through_sqs_to_a_worker`: the Embedding Model fails once, the ingestion's retry goes through Floci to a real worker, and the Document becomes Ready.
6. **Messages carry identifiers only.** The test in 1 decodes each message on the queue: arguments are only the row ids (plus a re-embed's attempt number and a Project deletion's actor id and time). `test_every_job_but_the_health_probe_ignores_its_result` reads the headers from SQS.
7. **Task-seam test with the publisher fake.** `test_job_publisher.py::test_evaluation_and_suggestion_runs_go_to_the_runs_queue_and_other_jobs_to_general` sends every operation of the port through the recording fake and asserts each job's queue.
8. **The real-worker tests run on Floci, and CI has it.** `test_worker_health.py`, `test_telemetry.py`, `test_logging.py` and `test_job_queues.py` start real workers (in process, and as `celery -A app.worker.main` processes) against Floci, on per-xdist-worker queues (`tests/worker_resources.worker_queue_name`, `tests/sqs.py`). `make services` starts Floci too, and `backend.yml` runs it (with `TEST_SQS_ENDPOINT_URL`).
9. **The end-to-end suite passes on the Compose stack.** See "CI runs" below.
10. **Development guide.** `docs/development.md`: `make dev` and `make services` list Floci, the URL list has port 4566 and the queue names, and "Jobs go through SQS" under Background jobs lists routing, predefined queues, every setting, the local stack and the tests. `.env.example` lists the settings; the README's diagram and stack table say SQS (the two pools are 22-04/22-08).
11. **Highest seam, 100% coverage.** Full backend gate below.
12. **GLOSSARY / ADRs.** No new domain terms: queues are infrastructure, which the glossary does not cover. ADR-0021 already records the decision; nothing here changes it.

**Gate (2026-11-26, local, with Postgres, Redis, RustFS and Floci running):** ruff, `ruff format --check` and `mypy --strict` (521 files) pass; `make check-client` up to date; `make link-check` clean. Backend suite in 12 chunks of `pytest -n 3`: 3306 passed, 0 failed, every chunk on its first attempt; combined coverage 100% (17158 statements, 2178 branches, none missed). No frontend code changed; frontend lint, typecheck and Vitest were rerun with it. `make infra-check` was not rerun: no Terraform or `task-settings.json` change.

**CI runs:** the pushed commit runs `backend.yml` (with Floci from `make services`) and `e2e.yml`, which builds the Compose stack (with the `floci` service), waits for the health checks (the worker answers the health probe through SQS), seeds the demo through SQS and runs the whole Playwright suite. Their results are added below once the runs finish.

## Gaps and best guesses

- **Deferred (needs a live deploy):** jobs going through real AWS SQS with the task roles' permissions (no `ListQueues`/`CreateQueue`, the region from `AWS_REGION`) is proven only by ticket 22-09. Nothing here called AWS.
- **A worker stopped mid long poll on Floci** can keep that ReceiveMessage open for up to the wait time (10 s) and take the next message sent, which then stays hidden for the queue's visibility timeout. ADR-0020 covers it: the sweeper sends a job queued too long again. The logging tests' service processes use queues of their own so no other test's message goes to such a wait.
- **Static keys are `SQS_ACCESS_KEY_ID`/`SQS_SECRET_ACCESS_KEY`**, not `AWS_*`, following `OBJECT_STORE_ACCESS_KEY_ID`: setting `AWS_*` in compose would also reach every other boto3 client (Bedrock, KMS, SES). On AWS both are unset and the task role is used.
- **`pycurl` is pinned below 7.46.** Celery's SQS consumer (kombu) needs pycurl, and 7.46+ deprecates calls kombu still makes (the test suite turns warnings into errors).
- **Retries stay countdowns** (held by the receiving worker) rather than SQS `DelaySeconds`; both fit the five-minute cap, and countdowns keep the message format the same as before.
- **The README** gained only the SQS node and stack-table wording; the two worker pools and the cost table are 22-04 and 22-08.
