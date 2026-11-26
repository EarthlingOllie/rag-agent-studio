# 02: No job stays in progress after an error

**Ticket:** `21-02` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A sampled reply is judged and charged once however often its job runs, and an Evaluation Run, Suggestion run or Live Verdict that hits an unexpected error ends in a state a person can see instead of staying in progress.

**Blocked by:**
- None

**Status:** done

- [x] The Live Verdict job does nothing unless the verdict is Pending; a second run after the first finished makes no judge call and records no spend
- [x] Spend for a Live Verdict is recorded in the same conditional update that stores the verdict, so two copies racing record it once; no row lock is held across the judge call
- [x] An Evaluation Run whose job raises an unexpected error ends as Failed with a readable reason and frees the Agent for another Run
- [x] A Suggestion run whose job raises an unexpected error ends as Failed, and its check Run, if one was started, is ended too
- [x] A Live Verdict whose job raises an unexpected error becomes an Error, which the Live score leaves out
- [x] A Suggestion run that finds its check Run already in progress no longer crashes: it settles by the same rule
- [x] Tests count judge calls on the fake chat model and read spend back through the API
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Tests: `backend/tests/integration/test_job_errors.py` (API and task seams; each test failed before the change).

- **Live Verdict guard.** `judge_live_verdict` (`app/evaluation/live.py`) returns at once unless the verdict is Pending. `test_a_second_run_of_a_live_verdicts_job_makes_no_judge_call_and_records_no_spend` runs the held-back job twice: one judge call on the fake chat model, the same verdict, and the spend read through the Evaluation budget API equals the one Cost.
- **Spend in the conditional update.** The outcome is stored with one `UPDATE … WHERE status = 'pending' RETURNING`, and `add_spend` runs in that transaction only when it hit. The read transaction is committed before the judge is asked, so no row lock is held across the call. `test_two_copies_of_a_live_verdicts_job_racing_record_its_spend_once` holds both copies inside the judge at once with a barrier, so neither can hold a lock the other waits on. Both pay the judge, and the spend is recorded once.
- **Evaluation Run catch-all.** `run_evaluation` (`app/evaluation/job.py`) wraps the job. An unexpected error ends the Run `failed` with "The Run stopped on an unexpected error. What it answered is kept; run it again." The answers it already gave are kept. A Run that is no longer running stops before its next answer. `test_an_evaluation_run_whose_job_raises_unexpectedly_fails_and_frees_the_agent` starts another Run (202).
- **Suggestion run catch-all.** `run_suggestion` (`app/suggestions/service.py`) wraps the job. An unexpected error ends the run `failed` ("The Suggestion run stopped on an unexpected error. Start a new one."). A check Run that is still in progress is ended `failed` too, through `fail_check` in `app/evaluation/suggestion_check.py`. A run that was already cancelled stays cancelled, and a check that already finished is kept. Tests: `test_a_suggestion_run_whose_job_raises_unexpectedly_fails`, `…_cancelled_before_an_unexpected_error_stays_cancelled`, `…_that_raises_after_its_check_finished_keeps_the_check`.
- **Live Verdict catch-all.** An unexpected error makes a Pending verdict an Error ("Judging stopped on an unexpected error; this reply is left out of the Live score."). `test_a_live_verdict_whose_job_raises_unexpectedly_is_an_error_left_out_of_the_score` reads it as an Error, and the Version KPIs' Live score counts only the judged reply.
- **Check Run already in progress.** `test_a_suggestion_run_that_finds_its_check_run_in_progress_fails_and_ends_it` kills the first copy, with a `BaseException` that skips all error handling, once the check Run is started. The Suggestion is then Checking and the check Run is Queued. A second delivery used to crash in `start_check` with `RunInProgressError`. It now settles by the catch-all: the Suggestion is Failed, the stranded check Run is Failed with the reason, and the Agent can start a Run (202).
- **Money read back.** Judge calls are counted on the fake chat model, and spend is read through `GET …/evaluation-budget`.
- **Coverage and lint.** The whole backend suite was run to completion with one combined coverage report: 3,171 passed. Memory on the shared machine was too tight for one `-n 4` run, so it ran in four parts with `--cov-append`. Every file this ticket changes is at 100% line and branch coverage: `evaluation/job.py`, `live.py`, `models.py`, `suggestion_check.py` and `suggestions/service.py`. The only lines not covered are in `app/storage/s3.py` and `app/seed/runner.py` (lines 94-96), and only RustFS exercises them. RustFS (`make services`) cannot run in this environment, so the 11 RustFS tests in `test_object_store.py` and `test_seed.py` failed with a connection error to localhost:9000, and the total was 99%. This ticket does not touch those two files, so with RustFS running the gate stands as it did before the change. One other test, `test_retrieval_probe_index.py::test_the_index_finds_a_projects_chunks_behind_other_projects_nearer_ones` (HNSW retrieval, also untouched), failed once under parallel load and passed 3 times out of 3 on its own. `ruff check`, `ruff format --check` and `mypy` are clean.
- **Glossary.** No new terms. The entries for Evaluation Run, Suggestion run and Live Verdict now cover unexpected errors. No ADR changed: this applies ADR-0020's catch-all as written.

## Gaps / best guesses

- A second delivery of a Suggestion run still gathers evidence again and calls the proposer again before it fails. Claiming the run from Queued only is ticket 21-06.
- When two Live Verdict copies overlap, both still pay the judge. The criterion asks only that spend be recorded once. Stopping the second paid call needs a claim, which is ticket 21-03 and 21-07.
- An unexpected error inside a Suggestion's check is caught by the Run's own catch-all. The check ends Failed and the Suggestion completes with a failed check, which is a warning as today. Only errors outside the check fail the Suggestion.
- The coverage gate is 100% everywhere except the RustFS-only lines in `app/storage/s3.py` and `app/seed/runner.py`. RustFS could not run here, so a run with `make services` up should confirm the full gate.
- No new paragraph in `docs/development.md`. No module, route or migration was added, and specs 14 to 16 keep no paragraphs there.
