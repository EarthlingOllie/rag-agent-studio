# 07: Lost Live Verdicts

**Ticket:** `21-07` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A sampled reply whose judging job was lost or whose worker died is judged within minutes, tried once more at most, and then set to Error, so no Live Verdict stays Pending.

**Blocked by:**
- `21-02`
- `21-03`

**Status:** done

- [x] A Live Verdict Pending for longer than its threshold is re-sent by the sweeper once
- [x] A Live Verdict still Pending after its one re-send becomes an Error, which the Live score leaves out
- [x] A re-sent verdict whose first job is somehow still running is judged once and its spend recorded once
- [x] A verdict whose reply was Purged before the re-send is skipped, as today
- [x] Live Verdicts already stuck on Pending when this ships are handled by the first sweep
- [x] The threshold and the number of re-sends are settings
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seams: the API seam with the task seam, as the [shared test seams](../../specs/README.md#shared-test-seams) name them. A reply is sampled through the widget; a lost or held message comes from the Job publisher fake (`jobs` fixture); a worker that dies mid-judgement is a scripted judge raising `JobKilled`, which skips the job's error handling as the kill switches do; the sweeper task is called directly with the controllable clock. Outcomes are read through the Trace (Live Verdict), the Version KPIs (Live score) and the Evaluation budget (spend); judge calls are counted on the scripted chat model. New tests: `backend/tests/integration/test_lost_live_verdicts.py`; `test_job_errors.py` has its racing-copies test updated.

1. **Re-sent once after its threshold.** `app/evaluation/live_jobs.py` adds `LIVE_VERDICTS` to the sweeper's `POLICIES` (`app/jobs/tasks.py`). Its `JobTable` (`LiveVerdictRows`) picks a verdict Pending for the threshold since its job was last sent (`queued_at`, or `created_at` before any resend); `recover` sends it again with the dead copy's claim cleared, counts the resend and restarts `queued_at`. Tests: `test_a_live_verdict_whose_job_never_reached_the_queue_is_judged_after_its_threshold` (nothing at 4:59, re-sent and judged at 5:00, one judge call, traced as `pending too long`, counted in the Live score) and `test_a_live_verdict_whose_worker_died_while_it_was_judged_is_judged_once_more` (killed at the judge, judged after the sweep, spend equals the stored Cost).
2. **Still Pending after its re-send: Error, left out of the Live score.** When `resends` has reached the setting, `recover` sets the verdict to `error` with the reason "Judging was lost and sent again without finishing; this reply is left out of the Live score." `test_a_live_verdict_still_pending_after_its_resend_is_an_error_left_out_of_the_score`: lost twice, the threshold restarts with the resend, then Error; no judge call; Live score `n` is 0; later sweeps leave it alone.
3. **First job still running: judged once, spend once.** The job claims the verdict (`_claim`, one conditional update while Pending and unclaimed) before it asks the judge, and every settle is conditional on Pending and on this copy's claim or none, with the judged settle also gating the spend. `test_a_resent_live_verdict_whose_first_job_is_still_running_is_judged_and_charged_once`: the first copy is held at the judge, the sweep re-sends and the new copy stores the judgement; when the first copy's judge returns, its settle finds the verdict settled and it stores and spends nothing (the verdict and spend are unchanged). `test_a_resent_live_verdict_the_first_job_finished_meanwhile_is_not_judged_again`: the first copy finishes after the sweep and before the resend arrives; the resend finds nothing to claim (one judge call). `test_a_second_copy_of_a_live_verdicts_job_while_the_first_judges_makes_no_judge_call` (test_job_errors.py, replacing the 21-02 racing test that expected two judge calls): a second copy while the first holds the claim exits without calling the judge.
4. **Purged before the re-send: skipped.** `test_a_live_verdict_whose_reply_was_purged_before_the_resend_is_skipped`: the Conversation is deleted (its Messages Purged) while the job is lost; the resent job settles the verdict `skipped` and the judge is never called, as before.
5. **Stuck before this shipped.** Migration `0072_live_verdict_claims` adds `queued_at`, `resends` (default 0) and `claim_id` to `live_verdicts`. Verdicts already Pending keep no send time and no claim, so the first sweep takes them as Pending since they were created. `test_live_verdicts_stuck_on_pending_before_this_shipped_are_handled_by_the_first_sweep` builds both shapes (job lost; worker died mid-judge) with those columns cleared, and one sweep three days later judges both. The upgrade and downgrade round trip (`test_migrations.py`) covers the migration.
6. **Settings.** `LIVE_VERDICT_PENDING_SECONDS` (default 300) and `LIVE_VERDICT_RESENDS` (default 1) in `backend/app/core/settings.py`, read at each sweep. `test_the_threshold_and_the_number_of_resends_are_settings` checks the defaults and that 60 s with no resends makes a lost verdict an Error at the first sweep after a minute.
7. **Seams and coverage.** Every test above runs at the API seam with the task seam. The new and changed modules (`app/evaluation/live.py`, `app/evaluation/live_jobs.py`, `app/jobs/reliability.py`, `app/jobs/tasks.py`) have every line and branch run by the suite; see the local run below.
8. **Glossary and ADRs.** The Live Verdict entry in `GLOSSARY.md` already said a verdict is judged once and tried once more, then Error (amended with the spec); it now also says a lost job counts and when the retry happens. ADR-0020 is unchanged; this ticket applies it. `docs/development.md` gains a "Lost Live Verdicts" paragraph and the sweeper row names this ticket.

## Gaps and best guesses

- **Best guess:** Live Verdicts get no heartbeat. The job is under two minutes (the judge times out at 60 s; the [audit](./research/job-reliability-audit.md) says `created_at` is enough), so one threshold, Pending for 5 minutes since the job was last sent, covers both a lost message and a dead worker, as the ticket's single "threshold" setting suggests.
- **Best guess:** the generic sweeper gained `JobTable.stale_rows`, `overdue_rows` and `stale_reason` so a job type can pick its stale rows by its own rule and name its trace reason; ingestion keeps the defaults (same queries, same `no heartbeat` reason).
- **Best guess:** when the re-sends are used up, the sweeper still sends the job once more (the generic sweeper sends a message for every recovered row, as 21-03 recorded); that message finds the verdict an Error and does nothing. The recovery is traced as `pending too long` in both cases.
- **Best guess:** a copy given up for dead that is somehow still running can still finish its judge call, so in that one case two judge calls are paid for; only one judgement is stored and one spend recorded. A copy that finishes after the sweep but before the resend's copy claims stores its judgement (its settle accepts an unclaimed verdict), so the resend judges nothing.
- **Best guess:** a verdict whose resend is due is re-sent even if the month's Evaluation budget has since been spent, as a first delivery would be judged: sampling, not judging, checks the budget.
- **Test isolation:** the shared test database can hold Pending Live Verdicts left by earlier tests (held-back jobs), which the sweeper would now pick up in `test_interrupted_ingestion.py` too. Its autouse fixture's body moved to `settle_jobs_in_flight`, which also settles Pending Live Verdicts, and the new test file uses it.
- **Merge note:** sibling tickets add policies and migrations concurrently; `0072_live_verdict_claims` was renumbered from 0061 at the wave-5 integration and revises `0071_evaluation_run_claims`.
