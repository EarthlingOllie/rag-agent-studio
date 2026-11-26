# 05: Interrupted Evaluation Runs

**Ticket:** `21-05` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** An Evaluation Run whose worker died becomes Interrupted within minutes: it keeps the answers and Cost it has, frees the Agent, and the Editor can run it again.

**Blocked by:**
- `21-02`
- `21-03`

**Status:** done

- [x] Evaluation Runs gain a heartbeat, written while the Run works and at each answer
- [x] A Run with no heartbeat for 5 minutes is ended by the sweeper as `interrupted`, a new finished status beside completed, failed and cancelled
- [x] A Run is never marked Interrupted while its worker is alive, however long it takes; a second delivery of its job does nothing and pays for no answer
- [x] An Interrupted Run keeps its answers, Verdicts and Cost so far, and frees the Agent for another Run or Suggestion run
- [x] Reads that mean "latest result", the Evaluation summary, the Publish warning and Suggestion evidence treat an Interrupted Run as they treat a cancelled one
- [x] A Run Queued for more than 15 minutes is re-sent, including the Runs of a Rollout evaluation that were never queued because the API died partway through
- [x] Run history and the Run page show Interrupted with a one-line explanation and its partial results
- [x] "Run again" on an Interrupted Run starts a new Run with the same sides, after the usual estimated Cost
- [x] Runs already stuck on Running when this ships become Interrupted on the first sweep
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seams: the API seam with the task seam ([shared test seams](../../specs/README.md#shared-test-seams)) for the backend, and the network seam for the Studio. A Run starts through `startEvaluationRun` (or Rollout evaluation); a kill comes from the scripted chat model builder raising `JobKilled` as the Run builds its nth model; a lost message from the Job publisher fake (`jobs`); the sweeper task is called directly with the controllable clock. Outcomes are read through the Run, results, cases, Publish summary and Rollout endpoints, and the traces. New tests: `backend/tests/integration/test_interrupted_evaluation_runs.py` (8) and four in `frontend/apps/studio/src/projects/AgentEvaluation.test.tsx`.

1. **Heartbeat while the Run works and at each answer.** `run_evaluation` (`backend/app/evaluation/job.py`) claims the Run, then wraps the whole Run in `reliability.heartbeat`, and each answer's commit also writes one (`reliability.beat`, new in `app/jobs/reliability.py`). Migration `0061_evaluation_run_claims` adds `queued_at`, `claim_id` and `heartbeat_at` to `evaluation_runs`. Evaluation Runs are the second job type: `EVALUATION_RUNS` in `backend/app/evaluation/jobs.py`, listed in `POLICIES` (`app/jobs/tasks.py`).
2. **Five minutes without a heartbeat ends it `interrupted`.** `RunStatus.INTERRUPTED` is a new finished status. The policy's `recover` sets it, with `finished_at`, and clears the claim. `test_a_run_whose_worker_died_becomes_interrupted_keeping_what_it_answered_and_spent`: the sweep at 4:59 leaves the Run Running; at 5:01 it is Interrupted, and the trace records `evaluation.run <id>: no heartbeat`.
3. **Never interrupted while alive, and a second delivery does nothing.** The Run's `JobTable` sets `reclaims_stale=False` (a new `JobTable` field, default true), so the job claims from Queued only. `test_a_long_run_keeps_writing_heartbeats_and_a_second_delivery_does_nothing` holds an answer, moves the clock 10 minutes, and sweeps: nothing is recovered. A second delivery then builds no model, and the Run completes with one answer. `test_an_interrupted_run_cannot_be_cancelled_and_its_job_delivered_again_does_nothing` (with the sweeper's own resend) leaves the results unchanged and builds no model.
4. **Keeps answers, Verdicts and Cost; frees the Agent.** The first test reads progress 1/3, the answered repeat with its two Verdicts, and non-zero answering and judging Cost. `test_an_interrupted_run_frees_the_agent_for_another_run`: a start is refused while the Run is stuck (409), and accepted and completed once it is Interrupted. The partial unique index only covers queued and running, so it frees the Agent for a Suggestion run too.
5. **Latest result, summary, Publish warning, Suggestion evidence.** These reads already take only completed Runs (the set's latest result also takes failed ones): `service._with_latest`, `summary.publish_summary`, `failed_cases.failed_cases` (Suggestion evidence) and `rollout._agent_rollout`. So an Interrupted Run is left out as a cancelled one is. `test_interrupted_runs_count_as_cancelled_ones_for_latest_results_and_publish` checks that the set's latest result still points at the earlier finished Run and that the Publish summary is unchanged. A Suggestion's check that was interrupted reads as cancelled (`suggestion_check._STATES`).
6. **Queued over 15 minutes is sent again, also for Rollout evaluation.** `add_run` records `queued_at`. `test_a_run_that_never_reached_the_queue_is_sent_again_after_fifteen_minutes` sends nothing at 14 minutes and sends again after 15 (`queued too long` trace), and the Run completes. In `test_rollout_runs_never_queued_because_the_api_died_partway_are_sent_again`, the API sends one Run of three and loses the others; one sweep sends both, and every Agent's Rollout state finishes.
7. **Run history and Run page.** `AgentEvaluation.tsx`: the Status shows "Interrupted". The history row and the Run page notice say, in one line, that the worker stopped and the answers and spend are kept. The partial scores and answers show as for any finished Run. Test: "an Interrupted Run says why in the history and on its page…".
8. **Run again.** On an Interrupted Run started from the Agent, "Run again" opens the Evaluate dialog with the same sides and the Draft's Instructions (Version by number, Instructions Draft, or current when there was none or it is gone). It shows the estimated Cost, then starts through the unchanged `startEvaluationRun` contract. Tests check the estimate and the start body, cover each Instructions case, and confirm there is no Run again on a Rollout evaluation's Run or an archived Agent's Run.
9. **Runs stuck before this shipped.** The migration gives Running Runs no heartbeat, and Queued ones their `created_at` as queued time. `test_runs_stuck_on_running_before_this_shipped_become_interrupted_on_the_first_sweep` sets that shape and one sweep, with the clock not moved, ends it Interrupted. The migration round trip (`test_migrations.py`) passes; its downgrade turns Interrupted into Cancelled.
10. **Design system.** Only `Status` (flagged tone), `Notice` (warning), `button.secondary`, `text`/`ink` tokens and the existing Evaluate `Dialog` are used. There is no palette class and no `dark:`, and the palette ratchet passes (0 uses).
11. **Seams and coverage.** The backend tests are at the API plus task seam, and the Studio tests at the network seam. Checks: ruff, ruff format, mypy, `make check-client` (client regenerated), `make link-check`, frontend lint, typecheck and `pnpm test` (1284 passed, 100% thresholds hold). The backend suite ran in chunks with RustFS up, against its own test database and Redis, appending coverage. Unit and live tests: 470 passed. Integration first third: 614 passed. Middle third: 530 passed; the 4 `test_logging` subprocess tests timed out under memory pressure and passed on rerun (9 passed). Last third, split into four after the shared machine OOM-killed the larger chunks: 1601 passed. The one failure was the known HNSW probe flake (`test_the_index_finds_a_projects_chunks_behind_other_projects_nearer_ones`), which passes alone. Combined `coverage report` is 100% line and branch.
12. **Glossary and ADRs.** `GLOSSARY.md` already defines an Interrupted Evaluation Run under Evaluation Run (amended with the spec), so it is unchanged. ADR-0020 is unchanged; this ticket applies it, and paid jobs claim from Queued only. `docs/development.md` gains an "Interrupted Evaluation Runs" paragraph. The shared test seams note the chat model kill.

## Gaps and best guesses

- **Best guess:** "Run again" is offered only on Runs started from the Agent. A Rollout evaluation's or Suggestion's check's sides can't be started through the Run API, and Rollout evaluation (or a new Suggestion run) starts those again.
- **Best guess:** a Draft side runs again at the current Draft revision, since a Run can't pin an old one. When the Run had no Instructions Version, or that Version can't be found, the Current Instructions Version is chosen.
- **Best guess:** the explanation is fixed Studio text, not an `error_message` on the Run, as for cancelled Runs, so the API's `error_message` stays null.
- **Best guess:** the kill hook for the chat model is a test's model builder raising `JobKilled` (`app/jobs/faults.py`), not a `KillSwitch` on `FakeModelAdapters`. This keeps the shared fakes unchanged while sibling tickets edit them.
- **Out of this ticket (21-06):** a Suggestion run whose check Run is Interrupted stays Checking until 21-06 settles it as not checked. Until then its check reads as cancelled.
- **Migration numbering:** `0061_evaluation_run_claims` follows `0060_ingestion_claims`. Sibling tickets may also add a 0061, so integration may renumber.
