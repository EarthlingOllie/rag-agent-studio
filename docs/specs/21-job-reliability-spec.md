# Spec 21: Job reliability

**Status:** ready-for-agent · **Builds on:** [Spec 03](./03-projects-knowledge-base-spec.md), [Spec 07](./07-feedback-logging-comparison-spec.md), [Spec 14](./14-evaluation-loop-spec.md), [Spec 15](./15-live-evaluation-spec.md), [Spec 16](./16-suggestions-spec.md) · **Decisions:** [ADR-0020](../adr/0020-database-is-the-record-of-jobs.md), [ADR-0008](../adr/0008-full-line-and-branch-coverage.md) · **Research:** [job reliability audit](../tickets/21-job-reliability/research/job-reliability-audit.md)

## Problem Statement

Work the Studio does in the background can be lost or left stuck, and nobody is told.

- An Editor uploads a Document and it stays on Processing for good because the worker restarted during a deploy. Retry and replace are refused, and uploading the same file again is a Duplicate, so the only way out is to delete it.
- An Evaluation Run stays on Running after its worker died, and the Agent can start no other Run and no Suggestion run until someone thinks to cancel it.
- A Document sits on Queued for ever because the API saved it and then failed to reach the queue.
- An Owner deletes a Project, is told it was accepted, and nothing happens. Deleted Documents' files stay in storage.
- An alert email that should have gone out is never sent, and a Live Verdict can be judged and charged twice.

These faults exist today whenever a worker is stopped, the broker restarts or the API dies between two steps. They become frequent once workers run on interruptible capacity and scale in and out ([Spec 22](./22-lean-scalable-infrastructure-spec.md)), so this spec has to land first.

## Solution

Every background job either finishes or ends in a state a person can see, whatever dies, and any job can safely run twice.

- **Free jobs restart on their own.** A Document whose worker died goes back to Queued and is ingested again. A Re-embed carries on from where it stopped. Deletions are finished later. Scheduled jobs catch up on runs they missed.
- **Paid jobs end as interrupted.** An Evaluation Run whose worker died becomes **Interrupted**: it keeps the answers it has and shows what it spent, and the Editor decides whether to run it again. A Suggestion run that was interrupted before its proposal existed is Failed with that reason; one interrupted during its check keeps the proposal, shown as not checked.
- **Nothing loops.** A Document interrupted three times is Failed with the Failure category **interrupted**, and conversion is stopped after 30 minutes.
- **Nothing is charged twice.** A Live Verdict is judged once; a lost one is tried once more and then becomes an Error.
- **Deleting is visible.** A Project being deleted shows as **Deleting** and can't be restored; its rows and files go even if the first attempt is lost.
- **Alerts arrive.** An alert email that was due is sent, late if need be.

How it works is in [ADR-0020](../adr/0020-database-is-the-record-of-jobs.md): the database row is the record that a job must run, running jobs write a heartbeat, and one sweeper acts on rows that have waited too long or whose heartbeat has stopped.

## User Stories

### Documents

1. As an Editor, I want a Document whose ingestion was cut short to go back to Queued and be ingested again without my doing anything, so that a worker restart doesn't lose my upload.
2. As an Editor, I want a Document that was saved but never reached the queue to be picked up within minutes, so that it doesn't sit on Queued for ever.
3. As an Editor, I want a Document waiting for an automatic retry to be retried even if the broker lost the retry, so that "Retrying automatically" is always true.
4. As an Editor, I want a Document that keeps being interrupted to become Failed after three interruptions with the Failure category "interrupted" and a message that suggests Retry, so that one bad file doesn't restart for ever.
5. As an Editor, I want a manual Retry to start the interruption count again, so that I get three fresh attempts.
6. As an Editor, I want conversion that runs past 30 minutes to stop and the Document to be Failed with a conversion error, so that one huge scan can't hold a worker indefinitely.
7. As an Editor, I want a replaced Document whose new edition was interrupted to be ingested again the same way, while the current edition keeps answering, so that replacing is as safe as uploading.
8. As an Editor, I want an ingestion that restarts to leave exactly one set of Chunks, so that retrieval never sees duplicates.
9. As an Editor, I want a restarted ingestion whose older copy is somehow still running to produce one result, so that two workers can't both write the Document.
10. As an Editor, I want files of a Document I deleted, and of an edition I replaced, to be removed from storage even if the first attempt fails, so that deleted content is really gone.
11. As an Editor, I want the Expected source Stale flags refreshed after a new edition even if the worker died right after ingesting it, so that Evaluation Cases stay accurate.

### Re-embedding

12. As an Editor, I want a Re-embed whose worker died to carry on from the Chunks it had not yet done, so that a restart costs only the batch in flight.
13. As an Editor, I want a Re-embed that never reached the queue, or lost its retry, to start within minutes, so that the Project isn't left embedding every upload twice.
14. As an Editor, I want a Re-embed interrupted three times with no progress in between to fail, leaving the active Embedding Model unchanged and saying why, so that it can't restart for ever.
15. As an Editor, I want two copies of one Re-embed never to embed the same batch at once, so that a provider isn't paid twice.

### Evaluation Runs

16. As an Editor, I want an Evaluation Run whose worker died to become Interrupted within minutes, so that the Agent is free for another Run or a Suggestion run.
17. As an Editor, I want an Interrupted Run to keep the answers and Verdicts it has and show its Cost so far, so that I can see what I paid for.
18. As an Editor, I want an Interrupted Run left out of "latest result", the Evaluation summary and the Publish warning, as a cancelled Run is, so that partial results never pass for a full Run.
19. As an Editor, I want an Interrupted Run listed in the Run history with that status and a one-line explanation, so that I know it was not my doing.
20. As an Editor, I want to start the same comparison again from an Interrupted Run with one action, so that running it again is easy and is my choice.
21. As an Editor, I want a Run that hit an unexpected error to end as Failed with a reason, so that no error leaves it on Running.
22. As an Editor, I want a Run that never reached the queue to start within minutes, so that it doesn't block the Agent while doing nothing.
23. As an Editor, I want a Run never to be marked Interrupted while its worker is alive, however long it takes, so that a long Run is not cut short by the safety net.
24. As an Editor, I want the Runs of a Rollout evaluation to start even if the API died partway through queueing them, so that a Rollout doesn't leave some Agents waiting for ever.
25. As an Editor, I want a second delivery of a Run's job to do nothing, so that no answer is paid for twice.

### Suggestion runs

26. As an Editor, I want a Suggestion run interrupted before its proposal exists to become Failed with the reason "interrupted", so that I can ask again.
27. As an Editor, I want a Suggestion run interrupted during its check to keep the proposal I already paid for, shown as not checked, with its check Run Interrupted, so that the proposing Cost isn't wasted.
28. As an Editor, I want a second delivery of a Suggestion run's job to do nothing, so that evidence, proposed changes and Knowledge Base gaps are never duplicated and the proposer is not paid twice.
29. As an Editor, I want a Suggestion run that hit an unexpected error to end as Failed, so that it never stays in progress.
30. As an Editor, I want cancelling a Suggestion's check Run directly to settle the Suggestion as not checked, so that it isn't stranded on Checking.
31. As an Editor, I want a Suggestion run that never reached the queue to start within minutes, so that it doesn't block the Agent's Runs.

### Live Verdicts

32. As an Owner, I want a sampled reply judged once however many times its job is delivered, so that the Evaluation budget is charged once.
33. As an Owner, I want a Live Verdict whose worker died to be tried once more and then set to Error, so that none stays Pending for ever and none is retried without limit.
34. As an Owner, I want a Live Verdict that never reached the queue to be judged within minutes, so that the Live score isn't missing samples.
35. As an Owner, I want a Live Verdict that hit an unexpected error to become an Error, which the Live score already leaves out, so that it never stays Pending.

### Deleting a Project

36. As an Owner, I want a Project I delete to show as Deleting at once and be hidden from normal use, so that I know the request was recorded.
37. As an Owner, I want the deletion to finish even if its first attempt was lost, so that "accepted" always ends in "gone".
38. As an Owner, I want the Project's files removed from storage as well as its rows, even if the worker died between the two, so that nothing is left behind.
39. As a Member, I want a Project that is Deleting to refuse uploads, edits and Visitor messages, so that nothing new is written to something being removed.
40. As an Owner, I want to be told that a Deleting Project can't be restored, so that I'm not surprised.

### Alerts and scheduled work

41. As an Owner, I want the Token Budget exhausted, Evaluation budget spent, Block rate alert and Live score drop alert emails sent even if the process died between raising the alert and sending it, so that I never miss one.
42. As an Owner, I want an alert that reached some Owners before a failure to reach the rest afterwards, so that a partial send is completed.
43. As an Owner, I accept a rare second copy of an alert email in exchange for never losing one.
44. As an Owner, I want the Purge to run every hour, so that a missed run leaves Message text at most an hour past its Retention Window.
45. As an Owner, I want the Block rate alert check to cover every hour since it last ran, so that a spike during an outage is still noticed.
46. As an Owner, I want the daily reset of Token Budget alerts to happen on the next run after a missed midnight, so that the exhausted mark doesn't outlast its day by more than an hour.
47. As an Owner, I want usage rollups to stay correct when their job runs twice or late, so that Analytics never double counts.

### Operating it

48. As a developer, I want one sweeper that runs every minute and once when a worker starts, so that recovery doesn't depend on any single message arriving.
49. As a developer, I want the rows already stuck when this ships handled by the same rules on the first sweep, so that no clean-up script is needed.
50. As a developer, I want every threshold (heartbeat interval, how long before a job counts as dead, how long queued before a job is re-sent, the interruption cap, the conversion limit) to be a setting with a sensible default, so that they can be tuned without a release.
51. As a developer, I want a job that is re-sent while its first message is still waiting to run once, so that a busy period can't make work run twice.
52. As a developer, I want each recovery the sweeper makes recorded in the traces with the job and the reason, so that I can see how often work is interrupted.
53. As a developer, I want jobs published through one port with a fake that can lose or hold a message, so that these failures are tested without a broker.
54. As a developer, I want only the health probe to keep its result, so that the API stops subscribing to replies nobody reads.

## Implementation Decisions

- **The rule ([ADR-0020](../adr/0020-database-is-the-record-of-jobs.md)).** The row is the request. A job claims its row with one conditional update (queued, or in progress with a stale heartbeat), which also counts the attempt. It writes a heartbeat while it works and checks it still holds the claim before its final write. A job that can't claim exits without doing anything.
- **Job reliability module.** One deep module holds the claim, the heartbeat and the sweeper. Each job type supplies only its policy: what counts as queued and in progress, and what the sweeper does with a stale row. Job code never reads heartbeat columns itself.
- **Heartbeat.** Written every 30 seconds by a background task for as long as the job holds its claim, including during conversion and model calls. A job with no heartbeat for 5 minutes is dead.
- **Sweeper.** One task, every minute from Beat and once when a worker starts, under an advisory lock so two never overlap. For each job type it:
  - re-sends rows queued longer than 15 minutes;
  - returns stale ingestion and Re-embeds to their queued state and re-sends them, until the cap;
  - ends stale Evaluation Runs as Interrupted and stale Suggestion runs by the rule below;
  - re-sends a Pending Live Verdict once, then sets it to Error;
  - finishes requested Project deletions and drains the deletions table;
  - sends alert emails that are raised but not sent.
- **Queued too long.** The 15 minutes are longer than the longest automatic retry backoff. Re-sending is always safe because the claim makes a second message a no-op, so a false positive under load costs one wasted message.
- **Job publisher port.** Every job is sent through one port. The production adapter sends to Celery. The fake records what was sent and can lose or hold a message. A failed publish is logged and left to the sweeper, and the request that queued the job still succeeds, because the row is the record.
- **Ingestion.** The claim accepts a Queued row or a Processing row with a stale heartbeat. The interruption count is kept apart from the provider-retry count, and a manual Retry resets both. The third interruption sets Failed with the new Failure category `interrupted`. Conversion has a 30-minute limit that ends in the existing conversion error. The final write and the settle step check the claim. Follow-on work after a new edition (removing the old edition's files, refreshing Expected source Stale flags) is finished by the sweeper if the worker died before it.
- **Automatic retries.** The time of the next attempt is stored on the row, so a lost countdown is re-sent by the sweeper, and the attempt number comes from the row, never from the message.
- **Re-embed.** The job row carries the heartbeat. A stale job is re-sent and resumes. The cap counts interruptions with no new Chunks embedded in between; reaching it fails the job through the existing failure path.
- **Evaluation Run.** A new status `interrupted`, a finished status alongside completed, failed and cancelled. It keeps answers, Verdicts and Cost. Reads that mean "latest result", the Evaluation summary, the Publish warning and Suggestion evidence treat it as they treat cancelled. A catch-all ends a Run that raised as Failed with a reason. "Run again" starts a new Run with the same sides.
- **Suggestion run.** The first step claims from Queued only. A catch-all ends a run that raised as Failed. When the sweeper finds a stale run: with no proposal stored, Failed with the reason `interrupted`; with a proposal stored, it settles as not checked and its check Run becomes Interrupted. Cancelling a check Run directly settles its Suggestion as not checked.
- **Live Verdict.** The job exits unless the verdict is Pending and it wins the claim. Spend is recorded in the same conditional update that stores the verdict, so it can't be counted twice. One automatic re-send, then Error. No row lock is held across the judge call.
- **Project deletion.** The request sets a deleting mark and who asked, in the request's transaction. A Deleting Project is hidden from lists, refuses writes and Visitor messages, and can't be restored. The cascade writes the Project's storage prefix to the deletions table in its own transaction.
- **Deletions table.** One table of object keys or prefixes to delete, written in the transaction that removes the last reference to them (Document delete, replaced edition, Project delete). The sweeper deletes and then removes the row. Deleting a missing object is not an error, so this is safe twice.
- **Alert emails.** Each of the four alerts records when it was raised and, separately, when it was sent to each Owner. The sweeper sends what is raised and not sent. Password reset emails are unchanged.
- **Scheduled jobs.** The Purge runs hourly. The Block rate alert check records the last hour it covered and checks every hour since. The Token Budget alert reset keys on the UTC date, so a late run still resets the right day.
- **Celery settings.** Prefetch of one, late acknowledgement, results ignored except for the health probe. The default visibility timeout stays: a duplicate of a long job arrives, fails to claim and exits. Requeue-on-worker-lost stays off; the sweeper does that job with a cap.
- **Schema.** A heartbeat column on Evaluation Runs, Suggestions and Re-embed jobs. An interruption count and next-attempt time on Documents and staged editions. A deleting mark and requester on Projects. The deletions table. Sent-at columns for the four alerts. The last-covered hour for the block-rate check. The new Run status and Failure category.
- **API.** The Run status and Failure category enums gain their new values. Project responses gain the deleting state. No new endpoints except "run again" on a Run, which reuses the start-Run contract.
- **Studio.** The Run history, Run page and Suggestion page show Interrupted and not-checked states with a one-line explanation. The Documents list shows the interrupted Failure category with Retry. The Projects list shows Deleting.
- **Glossary.** Evaluation Run, Suggestion run, Live Verdict, Document status, Failure category, Re-embed and Project are amended in `GLOSSARY.md` with this spec.

## Testing Decisions

- **Good tests** start a job the way a person would, break something at a chosen moment, and assert what the API then shows. They never assert on heartbeat columns or on how the sweeper is built.
- **API seam with the task seam.** Each job is started through the API action that queues it. The sweeper is called directly as a task, as Beat jobs already are. The controllable clock moves time past each threshold.
- **A killed worker.** The existing fakes (converter, embedder, chat model, object store) gain a hook that aborts the job at a chosen point without running its error handling. This is the only way tests simulate a kill.
- **A lost or held message.** The Job publisher fake drops or holds the message. Tests then run the sweeper and assert the job ran once.
- **Twice-safety.** Each job is applied a second time after it finished, and a second time while the first copy still holds its claim. Prior art: the Evaluation Run and Project deletion tests that apply a task twice.
- **What is covered, per job type:** never published; killed before the claim; killed mid-work; killed after the final commit but before follow-on work; an unexpected exception; delivered twice; two copies at once; the cap reached; and rows already stuck before the first sweep.
- **Money.** Tests count calls on the fake chat model and embedder and read spend back through the API: one judge call and one spend entry per Live Verdict, no second proposer call, no batch embedded twice.
- **Emails.** The in-memory outbox shows each alert sent at least once across a kill placed between raising and sending, and completed for the remaining Owners after a partial send.
- **Scheduled jobs.** With the controllable clock: a skipped midnight, a skipped Purge and several skipped block-rate hours all catch up on the next run.
- **Frontend, network seam.** The Interrupted Run in history and on its page, "run again", the not-checked Suggestion, the interrupted Failure category with Retry, and the Deleting Project.
- **End-to-end (Playwright).** One journey: a Document's ingestion is interrupted (a test-only switch on the fake converter), it returns to Queued and becomes Ready, with axe checks on the Documents list.
- **Coverage.** Every sweeper branch has a test (ADR-0008). The test that asserts the Beat schedule and the task list is updated for the sweeper and the hourly Purge.
- **Migrations** are covered by the existing upgrade and downgrade round trip.

## Out of Scope

- Changing the broker, the worker's capacity or how it scales ([Spec 22](./22-lean-scalable-infrastructure-spec.md)).
- Resuming an Evaluation Run or Suggestion run from where it stopped.
- The Studio's worker health indicator, which can show the worker as down when both of its slots are busy with long jobs.
- The brief block on deleting a Document while a Run answer that references it is being judged.
- A Live Verdict sample that may be skipped when a Visitor's browser disconnects at the very end of a reply.
- Finding and removing files orphaned in storage before this spec.
- Recording embedding spend, which the application doesn't track today.
- A second copy of a password reset email.

## Further Notes

- The order that keeps each step shippable: the Live Verdict guard and the catch-alls (no migration); the publisher port; heartbeats and the claim; the sweeper for queued and stale rows; the deletions table and Project deletion; the cap and conversion limit; alerts and scheduled jobs.
- An interrupted model or judge call that was in flight when the worker died is paid for and not recorded. Nothing can recover that Cost, and it is at most one call per interruption.
- The thresholds trade recovery time against false alarms. Five minutes without a heartbeat is ten missed beats, so a live job is not mistaken for a dead one by a slow database.
- The [audit](../tickets/21-job-reliability/research/job-reliability-audit.md) lists each defect with file and line references as of the day it was written.
