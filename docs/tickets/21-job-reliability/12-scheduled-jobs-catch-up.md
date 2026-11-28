# 12: Scheduled jobs catch up

**Ticket:** `21-12` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** The Purge, the Block rate alert check and the daily reset of Token Budget alerts all make up for a run that was missed while Beat was down, so a deploy never skips them.

**Blocked by:**
- None

**Status:** done

- [x] The Purge runs hourly; a missed run leaves Message text at most an hour past its Retention Window
- [x] The Block rate alert check records the last hour it covered and checks every hour since, so a spike during an outage is still alerted on
- [x] The Token Budget alert reset keys on the UTC date: a run after a missed midnight resets the day that ended
- [x] Usage rollups stay correct when their job runs twice or late (already true; a test pins it)
- [x] The test that asserts the Beat schedule reflects the hourly Purge
- [x] Tests use the controllable clock to skip a midnight, a Purge and several block-rate hours
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Tests are at the task seam (each Beat task called directly, as of the controllable clock's time) with assertions on API responses and sent emails, in `backend/tests/integration/`.

1. **Hourly Purge.** `retention-purge` in `backend/app/worker/celery_app.py` is now `crontab(minute="35")`: every hour, half an hour after that hour's rollup (the 00:05 rollup still finalises the previous day before the 00:35 Purge). The Purge already purges everything past its window as of its run, so the next run makes up a missed one: `test_retention.py::test_a_skipped_purge_is_made_up_by_the_next_hourly_run` skips the 09:35 run on the day a Conversation passes its window and the 10:35 run purges it.
2. **Block rate catch-up.** New column `agents.block_rate_checked_at` (migration `0068_block_rate_checked_at`): the end of the last hour the check covered for the Agent. `app/analytics/alerts.py::check_block_rates` first checks every hour since then that holds Visitor replies of the Agent and ended before the run (`_missed_hours`, oldest first), then the hour up to the run for every Agent, then records the run's time (never moving it back). `test_guardrail_analytics.py::test_a_spike_during_an_outage_is_alerted_on_by_the_next_run` stops Beat for four hours with an attack in the second; the next run emails the Owner, clears the alert (the current hour is calm), and the run after does not email again. `test_a_run_by_hand_for_an_earlier_time_doesnt_move_the_covered_hour_back` pins the "never back" rule.
3. **Token Budget reset on the UTC date.** `clear-token-budget-alerts` is now hourly (`crontab(minute="0")`); `clear_budget_alerts` already cleared flags raised before the current UTC date. `test_token_budget.py::test_a_run_after_a_missed_midnight_resets_the_day_that_ended` (run at 01:00 after a skipped midnight) and `test_a_late_run_keeps_an_alert_raised_on_the_new_day` (a flag raised at 00:30 survives the 01:00 run).
4. **Usage rollups twice or late.** Already pinned by `test_version_metrics.py::test_rollups_are_idempotent` (three runs, one 30 minutes late, same rollups) and `test_days_missed_by_the_task_are_caught_up` (three missed days finalised by one run). The hourly Purge relies on the same rollup gate, unchanged.
5. **Beat schedule test.** `test_retention.py::test_the_beat_schedule_purges_hourly_after_the_rollup` asserts the Purge runs every hour at :35 and each hour's rollup runs before it; `test_token_budget.py::test_the_beat_task_clears_the_alert_flags_at_midnight_utc` asserts the hourly reset.
6. **Controllable clock.** The tests above skip a midnight (`clock.advance(timedelta(hours=16))`), a Purge (the 09:35 run) and several block-rate hours (four hours of `clock.advance`).
7. **Coverage.** The changed modules (`app/analytics/alerts.py`, `app/worker/celery_app.py`, `app/embed/tasks.py`, `app/retention/tasks.py`, `app/retention/service.py`) are at 100% line and branch coverage; every branch of the catch-up (no missed hours, missed hours, scoped and unscoped checks) is exercised. The rest of the backend suite passes; the only tests not run here are the ones that need RustFS (`test_object_store.py`, one in `test_seed.py`), and the only lines they leave uncovered are in `app/storage/s3.py` and `app/seed/runner.py`, which this ticket does not touch.
8. **Glossary and ADRs.** No new domain terms. `GLOSSARY.md` updates Budget alert (hourly reset on the UTC date), Block rate alert (catch-up) and Purge (hourly). ADR-0020 already says the scheduled jobs restart on their own; no decision changed. `docs/development.md` gains a Scheduled jobs section.

## Gaps / best guesses

- The last-covered hour is kept per Agent, not once for the whole check: an Agent never checked before (a new column, or a new Agent) starts from its first run with no catch-up, and per-Agent state keeps the shared test database's Agents from different tests' clocks out of each other's way.
- Catch-up hours are steps of an hour from the last covered hour, and only hours with Visitor replies of the Agent are checked; a quiet hour in between does not clear and re-raise an alert raised earlier in the same catch-up. There is no cap on how far back it goes.
- A catch-up email uses the same wording ("the last hour's") as a live one; it describes the hour that spiked, not the hour before the email.
- Migration `0059` was numbered off `0058`; sibling tickets of spec 21 adding migrations in parallel will need their revision chain rebased at merge. When main's spec 20 (Calls, migrations 0059..0067) was merged in, spec 21's ten migrations were renumbered after it, 0068..0077, so this one is now `0068_block_rate_checked_at` and revises `0067_call_rollups`.
