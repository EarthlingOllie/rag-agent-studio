# 11: Alert emails always arrive

**Ticket:** `21-11` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** The Token Budget exhausted, Evaluation budget spent, Block rate alert and Live score drop alert emails reach every Owner even if the process died between raising the alert and sending it.

**Blocked by:**
- `21-03`

**Status:** done

- [x] Each of the four alerts records when it was raised and, separately, when it was sent to each Owner
- [x] The sweeper sends any alert that is raised and not yet sent, to the Owners it has not reached
- [x] A kill between raising and sending results in the email being sent by the next sweep
- [x] A send that reached some Owners before failing is completed for the rest
- [x] An alert is raised once per period as today; a second email to one Owner is possible only if the process died after sending and before recording it
- [x] The Token Budget exhausted email, sent today from the API process, follows the same path
- [x] Password reset and invite emails are unchanged
- [x] Tests use the in-memory outbox and place the kill between raising and sending
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seams: the API seam with the task seam, as the [shared test seams](../../specs/README.md#shared-test-seams) name them. Alerts are raised the way they are today: a Visitor's refused message through the widget API (Token Budget), a Live Verdict judgement queued by a Visitor's reply (Evaluation budget), and the hourly rollup task (Block rate and Live score drop). The sweeper task `jobs.sweep` is called directly with the controllable clock. Assertions are on HTTP responses and the in-memory outbox. New tests: `backend/tests/integration/test_alert_emails.py` (5 tests).

1. **Raised, and sent to each Owner, recorded separately.** Each alert keeps its raised flag as before (`agents.budget_exhausted_at`, `evaluation_spend.budget_spent_emailed_at`, `agents.block_rate_alert_at`, `agents.live_score_drop_alert_at`). Migration `0075_alert_emails` adds the `alert_emails` table: one row per Owner per raised alert, with `alert`, `raised_at`, the Owner (`member_id`, `to`), the rendered `subject` and `body`, and `sent_at`. `app/alert_emails/delivery.py`'s `raise_alert` writes the rows in the transaction that raises the flag.
2. **The sweeper sends what is raised and not sent.** `app/jobs/tasks.py` runs `send_alert_emails` after the job sweep. It sends every unsent row, oldest first, to the Owners on it. Rows already sent are skipped. Every test below sweeps a second time and checks nothing more is sent.
3. **A kill between raising and sending.** The outbox's kill switch (`outbox.kill_switch.arm("send to <address>")`, `app/mail/outbox.py`, the `KillSwitch` from `app/jobs/faults.py`) stops the process at the first send, after the raise has committed. The tests are `test_a_kill_between_raising_the_block_rate_alert_and_emailing_is_sent_by_the_next_sweep`, `test_a_kill_between_raising_the_token_budget_alert_and_emailing_is_sent_by_the_sweep` and `test_a_kill_between_spending_the_evaluation_budget_and_emailing_is_sent_by_the_sweep`. In each, the alert shows as raised through the API (or the judgement job is in `jobs.killed`), no email has gone, and the next sweep emails every Owner (not the Editor).
4. **A partial send is completed.** `test_a_live_score_drop_email_killed_part_way_through_the_owners_is_completed` kills at the second Owner: the first has the email, and the sweep sends to the second only. `test_a_refused_send_is_completed_for_the_rest_of_the_owners_by_the_sweep` has the mail server refuse one Owner (`outbox.refuse(address)`). The rollup finishes, the other Owner has the email, the refusal is logged, and the sweep completes it.
5. **Once per period; a second copy only after a kill between send and mark.** The rows are written only by the update that raises the flag, so the existing once-per-period guards are unchanged. The existing tests that check this still pass: `test_token_budget.py`, `test_evaluation_budget.py`, `test_guardrail_analytics.py`, `test_live_score_alert.py`. Each row is sent under `SELECT … FOR UPDATE SKIP LOCKED` and marked sent in the same transaction. A concurrent sender (the raiser and a sweep) therefore skips a row that is being sent or has been sent. A row is sent again only if the sender dies after `mailer.send` and before the commit. The token budget kill test also shows that a later refusal on the same day raises nothing.
6. **The Token Budget email from the API follows the same path.** `app/embed/service.budget_exhausted` (called by the widget API on a refusal or the reply that spends the budget) now records rows and sends them through `send_alert_emails`. The kill test drives it through the widget API: the request dies, and the sweep sends.
7. **Password reset and invite emails are unchanged.** `app/auth/service.py`, `app/auth/account_api.py` and `app/tenancy/invites_api.py` are untouched and still call the mailer directly. `test_password_reset.py` and `test_invites.py` pass.
8. **In-memory outbox, kill between raising and sending.** See items 3 and 4. A kill fires inside `OutboxMailer.send`, after the alert's transaction committed and before the email is appended to `outbox.sent`.
9. **Highest seam; coverage.** All five tests run at the API seam with the task seam. Every new line and branch is run by these tests or the existing alert tests. That includes the refused-send branch, the sweep with nothing to send, the budget update that raises nothing, and the Evaluation judgement that spends nothing. Ruff, ruff format and mypy pass. See Gaps for the suite run.
10. **Glossary and ADR.** `GLOSSARY.md` gains **Alert email**. ADR-0020 gains a paragraph on the one row-per-message table and the lock held across the send. `docs/development.md` gains an "Alert emails" paragraph and the sweeper row under Scheduled jobs.

## Gaps and best guesses

- **Best guess:** the Owners to email are fixed when the alert is raised, and each Owner's email is rendered then. An Owner added between the raise and a late sweep is not emailed. One removed in that gap is not emailed either, because their rows cascade away with the Member.
- **Best guess:** a send the mailer refuses is retried by every sweep (each minute) until it goes. There is no cap and no backoff, since an alert must never be lost.
- **Best guess:** sent rows are kept, with no pruning. They are small, one per Owner per alert, and they go when the Organisation, Agent or Member is deleted.
- **Best guess:** `evaluation_spend.budget_spent_emailed_at` keeps its name. It now means the alert was raised, and the comment on the model says so.
- **Migration number:** `0075_alert_emails` (renumbered from 0061 at the wave-5 integration) revises `0074_object_deletions`.
- **Knock-on change:** `budget_exhausted` now commits after loading the Agent, which expires it. The demo page's "spend the budget" route (`app/seed/demo_pages.py`) therefore reads the Agent's budget before calling it. `test_demo_pages.py` covers this.
- **Local run (2026-11-26):** the backend suite ran against a local PostgreSQL 16 and Redis, with RustFS up in Docker, in its own database (`studio_t2111`). Logs are in `/var/tmp/pg-21-02/chunks-2111/`. Memory was shared with the other wave-5 worktrees, so the run was in chunks. Chunks killed for lack of memory (exit 137) were run again in smaller groups, then file by file, all appending to one coverage file. Every test passed: 470 unit/live, then 531 + 192 + 190 + 330 + 1092 + 417 integration. `test_logging.py`'s 4 subprocess start-up tests timed out under that load and passed when run again on their own (9 passed). The combined coverage report shows 100% of lines and branches (`coverage3.txt`). Ruff, ruff format, mypy and `make link-check` pass.
