# 06: Interrupted Suggestion runs

**Ticket:** `21-06` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A Suggestion run whose worker died never stays in progress: it fails as interrupted, or keeps the proposal the Editor already paid for as not checked. A second delivery of its job changes nothing.

**Blocked by:**
- `21-05`

**Status:** done

- [x] The Suggestion run's first step claims from Queued only, so a second delivery does nothing: no evidence, proposed changes or Knowledge Base gaps are added and the proposer is not called again
- [x] Suggestion runs gain a heartbeat that covers gathering, proposing and checking
- [x] A stale run with no proposal stored becomes Failed with the reason `interrupted`
- [x] A stale run with a proposal stored settles as not checked, keeps its proposing Cost, and its check Run becomes Interrupted
- [x] Cancelling a Suggestion's check Run directly settles the Suggestion as not checked
- [x] A Suggestion run Queued for more than 15 minutes is re-sent
- [x] The Suggestion page shows the interrupted failure and the not-checked state with a one-line explanation
- [x] Tests count proposer calls on the fake chat model across a second delivery and across a kill in each phase
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seams: the API seam with the task seam ([shared test seams](../../specs/README.md#shared-test-seams)) for the backend, and the network seam for the Studio. A run starts through the Suggestions start endpoint; a kill comes from the scripted chat model builder raising `JobKilled` as the run builds its nth model (the proposer's, or a check answer's); gathering asks no model, so its kill replaces the job's evidence read; a lost message comes from the Job publisher fake (`jobs`); the sweeper task is called directly with the controllable clock. Outcomes are read through the Suggestion and Run endpoints and the traces, and every test counts the proposing calls the fake chat model answered. New tests: `backend/tests/integration/test_interrupted_suggestion_runs.py` (11) and one in `frontend/apps/studio/src/projects/AgentSuggestions.test.tsx` (another extended).

1. **Claims from Queued only; a second delivery does nothing.** `run_suggestion` (`backend/app/suggestions/service.py`) claims the run through `reliability.claim` with `SUGGESTION_ROWS` (`backend/app/suggestions/jobs.py`, `reclaims_stale=False`), moving it to gathering; a run that isn't Queued is left. `test_a_finished_runs_job_delivered_again_changes_nothing_and_proposes_nothing` delivers a completed run's job again: the Suggestion reads the same (1 evidence, 1 change, 1 gap) and the proposer count stays 1. The kill tests deliver again while the dead copy still holds the run, and after the sweep: nothing is added and the proposer is not called.
2. **Heartbeat through gathering, proposing and checking.** The job wraps the whole run, check included, in `reliability.heartbeat`. Gathering, proposing and checking are all in progress (`_SuggestionRows._in_progress`), and `reliability.holding` now uses each table's `_in_progress`, so the beat holds as the phase changes. `test_a_long_run_keeps_writing_heartbeats_and_a_second_delivery_does_nothing[proposing|checking]` holds the proposing call or a check answer, moves the clock 10 minutes and sweeps: nothing is recovered, a second delivery does nothing, and the run completes with one proposing call.
3. **No proposal stored: Failed, reason `interrupted`.** `SuggestionRunPolicy.recover` sets `failed`, `failure_reason` `interrupted` (new `SuggestionFailure`, exposed as `failure_reason` on the API) and `finished_at`. Tests kill while gathering and while proposing: at 4:59 the sweep leaves the run; after 5 minutes it is Failed as interrupted, the trace records `suggestions.run <id>: no heartbeat`, the proposer was never called, and the Agent can start another run.
4. **Proposal stored: not checked, proposing Cost kept, check Run Interrupted.** With a check Run, `recover` ends that Run Interrupted (if still in progress) and completes the Suggestion, freezing what the check spent. `test_a_run_killed_while_checking_keeps_its_proposal_not_checked`: the check `state` is `not_checked` with its `evaluation_run_id` kept, the Run reads `interrupted`, proposing and checking Cost are non-zero, both recoveries are traced, and a second delivery changes nothing.
5. **Cancelling the check Run directly.** `cancel_run` (`backend/app/evaluation/service.py`) calls `check_stopped` for a Run of kind `suggestion`, which completes a Suggestion still checking as not checked in the same transaction. A completed Suggestion whose check Run was cancelled or Interrupted reads `not_checked` (`_check_of`); a cancelled Suggestion's check still reads `cancelled`. Tests: the check's worker dead (`test_cancelling_a_suggestions_check_run_settles_it_as_not_checked`, the Agent is then free) and alive (`test_a_check_run_cancelled_while_its_job_is_alive_settles_as_not_checked`).
6. **Queued more than 15 minutes is re-sent.** `start_suggestion` records `queued_at`. `test_a_run_that_never_reached_the_queue_is_sent_again_after_fifteen_minutes` sends nothing at 14 minutes and sends again after 15 (`queued too long` trace); the run completes with one proposing call.
7. **Suggestion page.** `AgentSuggestions.tsx`: an interrupted failed run's notice says in one line that its worker stopped before the proposal was made and to start a new run; a not-checked Suggestion whose check Run stopped says its check Run was cancelled or interrupted, the proposal and its Cost are kept, the cost line says what the check cost before it stopped, and the Run detail link stays. Tests: "an interrupted run says its worker stopped…" and the check-states test's new case.
8. **Proposer calls counted.** Every test in the new file counts proposing calls on the scripted fake chat model (`Models.proposed`) across a second delivery and a kill in gathering (0), proposing (0) and checking (1).
9. **Design system.** Only the existing `Notice` (error), `text-ink-2` text and `Status` are used; no palette class, no `dark:`; the palette ratchet passes (0 uses).
10. **Seams and coverage.** Backend tests at the API plus task seam, Studio at the network seam. Checks run: ruff, ruff format, mypy, `make check-client` (client regenerated), `make link-check`, frontend lint, typecheck and `pnpm test` (1290 passed, 100% thresholds). Targeted backend tests (suggestions, evaluation, interrupted jobs, job errors, migrations) pass, with `app/suggestions/*`, `app/jobs/reliability.py` and `app/evaluation/suggestion_check.py` at 100% line and branch; the full suite runs at integration.
11. **Glossary and ADRs.** `GLOSSARY.md` already defined interrupted Suggestion runs under Suggestion run; the Suggestion's check entry now says a check Run cancelled directly or Interrupted leaves it "Not checked". ADR-0020 is unchanged. `docs/development.md` gains an "Interrupted Suggestion runs" paragraph.

## Gaps and best guesses

- **Best guess:** "a proposal stored" means the run has a check Run (it was checking). A run killed after the proposing call was paid but before its proposal was stored keeps its proposing Cost and fails as interrupted.
- **Best guess:** the interrupted failure is the `failure_reason` column with fixed Studio text, and `error_message` stays null, as for an Interrupted Evaluation Run.
- **Best guess:** a not-checked Suggestion whose check stopped keeps `state` `not_checked` and is told apart from "no Evaluation Set" by its `evaluation_run_id`; no new check state was added.
- **Best guess:** gathering reads no fake, so the gathering kill replaces the job's evidence step (`_gather`) with one raising `JobKilled`.
- **Changed test:** 21-02's `test_a_suggestion_run_that_finds_its_check_run_in_progress_fails_and_ends_it` expected a second delivery of a checking run to fail it; a second delivery now does nothing (the sweeper settles it), so it became `test_a_suggestion_run_that_raises_before_its_check_starts_fails_and_ends_it`, which still covers the check Run failing with its Suggestion.
- **Migration numbering:** `0076_suggestion_run_claims` revises `0075_alert_emails`; at the wave-8 integration it kept 0067 and 21-10's migration became `0077_project_deletions`.
