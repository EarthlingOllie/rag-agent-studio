# Background-job idempotency and reliability audit

Research for [spec 21](../../../specs/21-job-reliability-spec.md), which records the decisions taken on its open questions. Read at commit `819f40c`; nothing was run.
Paths are relative to `backend/` unless they start with `infra/`, `frontend/`, `docker-compose.yml` or `GLOSSARY.md`.

Every claim is marked **V** (verified: the cited lines were read) or **I** (inferred: reasoning from
verified code, or from Celery/Postgres behaviour not exercised here). Celery claims marked
"V (celery src)" were checked against the pinned versions' source (celery 5.6.3, kombu 5.7.0,
`uv.lock:337-338,1149-1150`), downloaded outside the repo.

## 0. Inventory

`app/worker/celery_app.py:17-27` includes 9 modules; `grep @celery_app.task` finds 11 tasks, all in
those modules. Nothing is missed and nothing is registered elsewhere. **V**

| Task name | Defined at |
|---|---|
| `worker.health_check` | `app/worker/tasks.py:4` |
| `documents.ingest` | `app/documents/tasks.py:47` |
| `documents.delete_objects` | `app/documents/tasks.py:69` |
| `evaluation.run` | `app/evaluation/tasks.py:33` |
| `evaluation.live_verdict` | `app/evaluation/tasks.py:44` |
| `projects.delete` | `app/projects/tasks.py:31` |
| `projects.re_embed` | `app/re_embedding/tasks.py:42` |
| `suggestions.run` | `app/suggestions/tasks.py:32` |
| `analytics.roll_up_usage` | `app/analytics/tasks.py:30` |
| `retention.purge_expired` | `app/retention/tasks.py:30` |
| `embed.clear_budget_alerts` | `app/embed/tasks.py:22` |

Configuration today (`app/worker/celery_app.py:34-61`): broker and result backend on the same Redis
URL, `result_expires=300`, eager switch, Beat schedule. No `task_acks_late`, prefetch, time limits,
`broker_transport_options`, retries, routes or `task_ignore_result`. **V**
Worker: `celery ... worker --concurrency=2`, prefork (`docker-compose.yml:131`,
`infra/modules/ecs/main.tf:16`; prefork confirmed by `worker_process_init` in
`app/worker/main.py:53`). No `stop_timeout`, Spot or autoscaling anywhere in `infra/` (grep). **V**
Worker task size 2 vCPU / 8 GiB for both processes (`infra/modules/ecs/variables.tf:100`). **V**

No use of `self.retry`, `autoretry_for`, `bind=True`, chains or `send_task`. The only in-task
enqueues are two `apply_async(countdown=...)` self-retries. **V**

## 1. Per-job table

Legend. Producer window: what exists if the process dies, or Redis is down, between the DB commit
and the publish. Kill-safety: SIGKILL of the worker mid-task. "Sequential" = the same job run again
after the first copy ended or died. "Concurrent" = two copies at the same instant.

| Job | Trigger | Producer failure window | Worst-case duration | Kill-safety | Twice, sequential | Twice, concurrent | Broker-loss recovery | Paid calls | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `documents.ingest` | API: confirm, replace, retry (`documents/api.py:474,737,775`); itself, `apply_async(countdown)` (`documents/tasks.py:54`) | Row committed QUEUED first (`documents/service.py:273,731,346`), then publish. Gap → QUEUED forever. **V** | Unbounded: Docling has no timeout or page cap (`documents/converter.py:41-66`); 50 MB upload cap (`core/settings.py:140`). Minutes to tens of minutes with OCR. **I** | **Unsafe.** `_start` commits PROCESSING (`pipeline.py:148,174`); a re-run returns `None` unless QUEUED (`:133-137`). Stuck PROCESSING forever. **V** | Safe: second run exits. **V** | Safe: `_start` takes `FOR UPDATE` on Document and Project (`pipeline.py:126`); second sees PROCESSING. **V** | None. QUEUED rows and countdown retries are orphaned. `documents.updated_at` / `staged_editions.updated_at` exist (`documents/models.py:90,122`), set at claim (`pipeline.py:139`), not while processing. **V** | Provider embeddings, active and pending model (`pipeline.py:182,256`). Never recorded. **V** | Fix: stuck on kill, stuck on lost message, no poison cap |
| `documents.delete_objects` | API after Document delete / replace (`documents/api.py:666,736`); ingestion (`pipeline.py:355,361,429`) | Keys exist only in the message; the Document row is already gone (`documents/service.py:661-663`). Gap → objects orphaned forever. **V** | Seconds | Safe (S3 delete is idempotent, `storage/s3.py:116-117`); with early ack a kill loses the rest of the keys. **V** | Safe. **V** | Safe. **V** | None, and no DB state to rebuild from. **V** | None | Fix: lost deletes leave "deleted" originals in S3 |
| `evaluation.run` | API start (`evaluation/api.py:880`), rollout loop (`evaluation/rollout_api.py:150-151`); inline from `suggestions.run` (`suggestions/service.py:879`, not enqueued) | Run committed QUEUED (`evaluation/service.py:896`), then publish. Gap → QUEUED forever, blocking the Agent. **V** | Up to 200 cases × 9 repeats × 2 sides = 3,600 answers (`evaluation/service.py:94`, `tenancy/models.py:70-71`), each an answer (HTTP timeout 120 s per call, `core/settings.py:97`) plus a judge call (≤60 s, `:165`). Hours. **I** | **Unsafe.** Commits RUNNING (`job.py:390-391`); re-run exits (`:388-389`). Any unhandled exception does the same: there is no `try` around the job (`job.py:386-427`, `evaluation/tasks.py:21-36`). **V** | Safe (exits). Test exists: `tests/integration/test_evaluation.py:629`. **V** | Safe: claim under `FOR UPDATE` (`job.py:387`). **V** | None. `evaluation_runs` has `created_at` and `finished_at` only; no `updated_at`/heartbeat (`evaluation/models.py:182-224`, `core/db.py:31-33`). **V** | Chat model, reranker, LLM classifier, judge per answer (`job.py:173-207,318`). Cost on the case result, committed with it (`:298,330,416`). **V** | Fix: stuck RUNNING blocks the Agent |
| `evaluation.live_verdict` | API, after a sampled Visitor reply (`embed/api.py:395-403`) | Verdict committed PENDING (`evaluation/live.py:105-106`), then publish. Gap → PENDING forever. **V** | ≤ judge timeout 60 s plus queries. **V** | Kill → PENDING forever (nothing written until the end, `live.py:234`). Paid judge call may be lost. **V** | **Unsafe**: no status guard (`live.py:179`); judges again, overwrites, `add_spend` again (`live.py:231`, `budget.py:134-141`). **V** | **Unsafe**: both judge (2 paid calls); the lock is taken only after judging (`live.py:210-212`); both add spend. **V** | None. PENDING + `created_at` is enough to detect (job is short). **V** | Judge (`live.py:196`). Spend counter `evaluation_spend` (`budget.py:127-159`). **V** | Fix: double charge and double record; no escape hatch |
| `suggestions.run` | API start (`suggestions/api.py:550`) | Row committed QUEUED (`suggestions/service.py:349`), then publish. Gap → QUEUED forever, blocking the Agent's Runs too. **V** | Gather + proposer (≤120 s, `core/settings.py:168`) + a whole Evaluation Run inline. Hours. **I** | **Unsafe.** Stays GATHERING / PROPOSING / CHECKING. Unhandled exceptions do the same (no `try`, `suggestions/service.py:803-880`). **V** | **Unsafe**: `_set_status(GATHERING)` matches any in-progress status (`service.py:568-571`), so a re-run restarts from the top: evidence inserted again (`:637-648`), proposer paid again (`:833`). If it was CHECKING, `start_check` raises `RunInProgressError` (`evaluation/service.py:774-775`), not in `_UNCHECKABLE` (`suggestions/service.py:686-692`): the task crashes, the Suggestion is left PROPOSING and its check Run stays RUNNING. **V** | **Unsafe**: both copies gather and propose; `_proposed` serialises on `FOR UPDATE` (`:740`), the second then crashes in `start_check` and rolls back. Evidence is doubled, proposer paid twice. **V** | None. `suggestions` has `created_at`, `proposed_at`, `finished_at`; no heartbeat (`suggestions/models.py:74-141`). **V** | Proposer (`service.py:833`); `proposing_cost_usd` overwritten by `_spent` (`:792-799`). The check's answers and judgements. **V** | Fix: stuck, duplicates, double pay |
| `projects.re_embed` | API when the Embedding Model changes (`projects/embedding_api.py:169`); itself (`re_embedding/tasks.py:49`) | Job committed RUNNING (`projects/embedding.py:162-170`), then publish. Gap → RUNNING forever. **V** | Chunks ÷ 64 provider calls (`core/settings.py:182`). Hours for a large Knowledge Base. **I** | Safe: resumable; each batch commits in `_step` (`re_embedding/job.py:163-173`); a kill loses at most one embedded batch. **V** | Safe: `_missing` skips what is written; inserts are `ON CONFLICT DO NOTHING` (`job.py:72-88,146`). **V** | Correct data, but both copies embed the same batch (`job.py:171,253`): paid twice. **V** | None. Job is RUNNING from birth; no QUEUED state, no heartbeat column (`re_embedding/models.py:27-63`). **V** | Provider embeddings (`job.py:253`). Never recorded. **V** | Fix: stuck RUNNING on lost message; double pay when concurrent |
| `projects.delete` | API (`projects/api.py:249`) | **No DB write at all**: `check_deletion` only reads (`projects/service.py:263-272`), the API rolls back and publishes (`projects/api.py:248-249`). The request exists only in Redis. **V** | One cascade transaction + S3 list/delete; minutes for a big Project. **I** | Kill before commit: rolled back, safe. Kill between commit (`projects/service.py:305`) and `delete_prefix` (`projects/tasks.py:27-28`): prefix orphaned for good, because the re-run finds no Project and returns `None` (`service.py:288-289`). **V** | Rows safe (test `tests/integration/test_project_deletion.py:294`); S3 as above. **V** | Safe: `FOR UPDATE` on the Project (`service.py:285-287`). **V** | None. Nothing in the DB says deletion was requested. **V** | None | Fix: silent no-op after 202; orphaned prefix |
| `analytics.roll_up_usage` | Beat, minute 5 hourly (`celery_app.py:50`) | n/a (Beat publishes) | Seconds to minutes; SQL only | Safe: one transaction, rolled back (`analytics/rollup.py:81-99`). Alerts: flag committed before email (see D14). **V** | Safe: full recompute and replace (`rollup.py:27-39`). **V** | Safe: `pg_advisory_xact_lock` (`rollup.py:82`); alert flags raised by atomic `UPDATE ... RETURNING` (`alerts.py:155-162,305-318`). **V** | Next tick catches up missed days (`rollup.py:42-65,83-87`). **V** | None | Safe, except alert emails and the hourly block-rate window |
| `retention.purge_expired` | Beat, 00:35 UTC (`celery_app.py:53-56`) | n/a | SQL only; long for a large backlog | Safe: one transaction for all Organisations (`retention/service.py:86-107`). **V** | Safe: filters `purged_at IS NULL` (`:47`). **V** | Safe; a second copy may re-stamp `purged_at` seconds later. **I** | Next day's run purges everything older than the cutoff. **V** | None | Safe; a missed tick delays the Purge by a day |
| `embed.clear_budget_alerts` | Beat, 00:00 UTC (`celery_app.py:45-48`) | n/a | Milliseconds | Safe. **V** | Safe (`embed/service.py:424-435`). **V** | Safe. **V** | Next midnight clears everything older. **V** | None | Safe; missed tick is cosmetic (D23) |
| `worker.health_check` | Beat every 300 s; API probe (`api/health.py:110`) | n/a | Instant | Safe | Safe | Safe | n/a | None | Safe |

## 2. Section-by-section findings

### A. The enqueue side

The abstraction is one `enqueue_*` coroutine per task, each
`await asyncio.to_thread(task.delay, ...)` (`documents/tasks.py:57-60,76-78`,
`evaluation/tasks.py:39-41,50-51`, `projects/tasks.py:43-50`, `re_embedding/tasks.py:52-54`,
`suggestions/tasks.py:38-40`). Routes call them after the service function has committed. **V**

Every call site is **commit, then publish**. None publishes before its commit, so "worker runs
before the row is visible" cannot happen. **V** The cost is the opposite window: a committed row
with no message, which nothing ever repairs.

| # | Call site | Commit | If the process dies or Redis is down in between |
|---|---|---|---|
| 1 | `documents/api.py:474` confirm upload | `documents/service.py:273` | Document QUEUED forever. Retry and replace are refused (`service.py:331-334,699-702`); the same file re-uploaded is a Duplicate. Only delete works. **V** |
| 2 | `documents/api.py:737` replace | `documents/service.py:731` | Staged edition QUEUED forever; Document itself keeps serving but can't be retried or replaced. **V** |
| 3 | `documents/api.py:775` retry | `documents/service.py:346` | QUEUED forever, as 1. **V** |
| 4 | `documents/api.py:666` delete objects | `documents/service.py:662` | Stored objects orphaned; no record of the keys. **V** |
| 5 | `documents/api.py:736` discarded edition's objects | `documents/service.py:731` | Orphaned. Also runs before 2: if it raises, ingestion is never enqueued. **V** |
| 6 | `evaluation/api.py:880` start Run | `evaluation/service.py:896` | Run QUEUED forever; the Agent can start no Run and no Suggestion run (`evaluation/service.py:774`, `suggestions/service.py:251`, index `evaluation/models.py:190-195`). Cancel works. **V** |
| 7 | `evaluation/rollout_api.py:150-151` loop | in `rollout.start_rollout` (docstring `evaluation/rollout.py:105`; commit not read, **I**) | Dying mid-loop leaves the remaining Agents' Runs QUEUED forever. **V** for the loop |
| 8 | `suggestions/api.py:550` | `suggestions/service.py:349` | Suggestion QUEUED forever; blocks the Agent's Runs. Cancel works; delete is refused (`suggestions/applying.py:254`). **V** |
| 9 | `embed/api.py:403` Live Verdict | `evaluation/live.py:106` | PENDING forever; no endpoint touches it. **V** |
| 10 | `projects/embedding_api.py:169` re-embed | `projects/embedding.py:170` | Job RUNNING forever; see D7. **V** |
| 11 | `projects/api.py:249` delete Project | none | Nothing happens; the Owner got 202 only if publish succeeded, so the real loss is Redis losing the message afterwards. **V** |
| 12 | `api/health.py:110` | none | Probe fails; harmless. **V** |

In-task enqueues:

- `documents/tasks.py:52-54`: the pipeline first commits QUEUED through `_requeue`
  (`pipeline.py:300,444-451`, also the model-changed path `:358-359`) and returns a delay; the task
  then publishes the next attempt. Today (early ack) a kill between the two, a failed publish or a
  Redis restart during the countdown leaves the Document QUEUED forever with the message
  "Retrying automatically (attempt n of m)" (`documents/limits.py:116-120`). **V**
- `re_embedding/tasks.py:47-49`: same shape; the job stays RUNNING forever. **V**
- `pipeline.py:355,361,429` call `delete_objects` (the enqueue) after their transaction. A failed
  publish at `:361` also skips `on_new_edition` at `:362`. **V**
- `on_new_edition` → `recheck_document` runs inline, not as a task
  (`documents/tasks.py:35`, `evaluation/expectations.py:121-133`). A kill between the swap commit
  (`pipeline.py:314-352`) and `:362` skips it; a re-run exits because the Document is Ready. Stale
  flags self-heal at the next Run (`job.py:247-251`). **V**

Seed path: the seed drives the same HTTP endpoints (`seed/runner.py:9`, ADR-0012), so it has the
same windows. For Evaluation Runs and Live Verdicts it flips the process-global
`task_always_eager` in the seed's own process (`seed/evaluation.py:22-30`). Ingestion goes to the
worker and the seed polls for up to 600 s (`seed/history.py:75-92`). **V**

Publishing with a result backend also subscribes the publishing process to a per-task result
channel unless `ignore_result` is set (celery `app/base.py:967-968`, `backends/redis.py:400-402`).
No task sets it, and only the health probe reads results. **V (celery src)** See D18.

### B. Broker loss

Redis is a single node (`infra/modules/cache/main.tf`, `num_cache_clusters = replicas + 1`,
checkov skip "A single node keeps the demo cheap"). **V** A restart loses queued messages, unacked
messages, countdown retries and results. **I** It also loses, from the same Redis: Token Budget
counters and rate limits (`embed/admission.py:4`) and pending uploads
(`documents/service.py:137`). **V**

Nothing re-enqueues from DB state today: there is no sweeper and no startup reconciliation. **V**

| Job | "Should be running but isn't" in the DB | Usable timestamp today |
|---|---|---|
| Ingestion | `documents.status` or `staged_editions.status` in (`queued`, `processing`) | `updated_at` on both tables. Fresh at enqueue and at claim; not refreshed while processing. Good for QUEUED; for PROCESSING only with a generous threshold or an added heartbeat. **V** |
| Evaluation Run | `evaluation_runs.status` in (`queued`, `running`) | `created_at` only. QUEUED age works. RUNNING has no timestamp; the only proxy is `max(evaluation_case_results.created_at)` (`job.py:282`). Column needed. **V** |
| Suggestion run | `suggestions.status` in the four in-progress values | `created_at`, `proposed_at`. QUEUED age works; the other phases need a column. **V** |
| Live Verdict | `live_verdicts.status = 'pending'` | `created_at`; enough, the job is under two minutes. **V** |
| Re-embed | `re_embed_jobs.status = 'running'` | `created_at` only; RUNNING covers both "waiting" and "working". Column needed. **V** |
| Project deletion | nothing | Needs a column (`deletion_requested_at`) or an outbox row. **V** |
| Object deletion | nothing | Needs an outbox table. **V** |
| Beat tasks | n/a | Recomputed at the next tick. **V** |

No table has an index on status for a sweeper; the partial unique indexes on in-progress Runs,
Suggestions and running Re-embeds already cover those three (`evaluation/models.py:190-195`,
`suggestions/models.py:83-88`, `re_embedding/models.py:33-38`). **V**

### C. Beat

- Schedule file: `--schedule=/tmp/celerybeat-schedule` (`infra/modules/ecs/main.tf:17`,
  `docker-compose.yml:135`). On ECS `/tmp` is a task-local volume on a read-only root
  (`infra/modules/ecs/main.tf` task definition, `mountPoints` `/tmp`), so every new Beat task
  starts with no file. **V** A fresh entry gets `last_run_at = now` (celery `beat.py:127`), so a
  crontab entry is next due at its next matching time: a tick missed while Beat was down is
  **skipped, not caught up**. **V (celery src)** Under compose, where the container's `/tmp`
  survives a restart, the entry is due at once after a missed time (`beat_cron_starting_deadline`
  unset). **I**
- Deploys stop Beat before starting the new one (`deployment_maximum_percent = 100`,
  `minimum_healthy = 0`, `infra/modules/ecs/main.tf:548-549`; `desired_counts.beat <= 1`,
  `variables.tf:140`). So there is a gap on every deploy and no overlap. **V**
- Double-fire: only possible with a persisted file plus a restart, or two Beats. All four tasks are
  safe twice (table above). **V**
- Missed tick, per task:
  - `usage-rollup`: next hour finalises every pending day (`rollup.py:83-98`). **V**
  - Block rate alert: the window is "the hour up to `at`" (`alerts.py:77-78`); an hour Beat
    missed is never checked, and a raised flag isn't cleared until the next run. **V**
  - Live score drop alert: cumulative as of `at`; self-heals. **V**
  - `retention-purge`: skipped for the day; the next run purges by cutoff, so everything is
    caught up one day late (`retention/service.py:88-106`). It also waits for rollup finality
    (`:95-105`), so a late rollup delays it the same way. **V**
  - `clear-token-budget-alerts`: `budget_exhausted` already treats a flag from an earlier day as
    no flag (`embed/service.py:392-394`), so emails are unaffected; only the Studio badge
    (`agents/api.py:133`, `budget_exhausted_at is not None`) stays on for a day. **V**
- Beat messages carry no `expires`. If the worker is down or both slots are busy for hours, the
  ticks queue up and all run later; harmless but noisy. **I**

### D. Poison jobs

- No attempt counter that caps anything. `documents.attempt_count` / `staged_editions.attempt_count`
  exist (`documents/models.py:86,120`), are incremented at every claim (`pipeline.py:138`), shown by
  the API (`documents/api.py:528`), reset only for a new staged edition
  (`documents/service.py:729`) and not on a user retry (`service.py:342-345`). **V**
- The only cap is the `attempt` kwarg in the message, which counts provider retries
  (`documents/tasks.py:48-54`, `pipeline.py:295`, `core/settings.py:177`). A redelivered message
  carries the same number. **V**
- Runs, Suggestions, Live Verdicts and Re-embed jobs have no attempt column. **V**
- With `acks_late` + `reject_on_worker_lost`, a child process that dies is requeued immediately,
  with no limit (celery `worker/request.py:612-621`). **V (celery src)** A PDF that OOMs or
  segfaults Docling/ONNX would loop for ever.
- A hard `time_limit` does **not** redeliver: with `acks_late` the message is acked on timeout
  (`worker/request.py:547-548`, `acks_on_failure_or_timeout` default true, `app/defaults.py:266`).
  **V (celery src)** The DB row is then stuck exactly as after a kill.
- Docling limits: none. `ThreadedPdfPipelineOptions(do_ocr=..., ocr_options=...)` only
  (`documents/converter.py:41-43`), `convert(stream)` with no page or size limit (`:64-66`). **V**
  Docling does offer `document_timeout` and `max_num_pages`/`max_file_size`. **I**
- Conversion, chunking and classification run in threads (`pipeline.py:200,224,233`), so a soft
  time limit raised in the main thread cannot stop them. **I**
- Where a cap belongs: the claim in `_start` (`pipeline.py:138`), which already counts. It needs a
  reset on a user's retry (or a separate interruption counter), and a "Failed, interrupted too
  often" outcome.

### E. Graceful shutdown and transaction boundaries

- SIGTERM starts a warm shutdown: stop consuming, wait for running tasks. **I** Every heavy task
  can exceed 120 s, so on Spot or scale-in the usual end is SIGKILL mid-task.
- After SIGKILL with `acks_late` on Redis, the message sits in the unacked set until
  `visibility_timeout` passes and another worker restores it (kombu `transport/redis.py:523-530`,
  default 3600 s `:1070`). **V (celery src)** So "long visibility timeout" directly means "slow
  recovery after a kill", and a timeout shorter than the longest task means a live task's message
  is delivered again while it runs.
- `REMAP_SIGTERM=SIGQUIT` with `worker_soft_shutdown_timeout` gives a bounded grace period and then
  a cold shutdown (celery `apps/worker.py:369-434`, `app/defaults.py:324`). **V (celery src)**
  That the cold shutdown returns unacked `acks_late` messages to the queue at once is **I**.
- A killed process drops its connections, so Postgres rolls back and releases every lock. **I**

Transaction boundaries per task:

| Task | Held across long work? |
|---|---|
| Ingestion | No. Claim is its own transaction (`pipeline.py:279-280`, commit `:174`); Docling, embedding and the scan run with no session; the final write is one short transaction (`:314-352`) with `FOR UPDATE` on the Document and `FOR SHARE` on the Project (`:369`). **V** |
| Evaluation Run | One session for the whole Run (`job.py:386`). A transaction is open across each answer. `_checks` updates `evaluation_expected_sources` (`job.py:247-251`) **before** the judge call (`:318`), and the commit is at `:416`: those row locks are held for up to the judge timeout. Document delete (`documents/service.py:643-647`), `recheck_document` (`expectations.py:127-133`) and case edits wait behind them. **V** |
| Live Verdict | One transaction across the judge call, but no row lock until after it (`live.py:178-212`). **V** |
| Suggestion run | Short sessions around each phase; the proposer call holds none (`suggestions/service.py:821-843`). `_proposed` holds the Suggestion and Agent row locks briefly (`:740,753`). Then the check behaves as an Evaluation Run. **V** |
| Re-embed | `_step` locks Project then job, writes, reads the next batch, commits; the embed call is outside (`re_embedding/job.py:163-173,252-256`). **V** |
| Project delete | One transaction for the cascade (`projects/service.py:285-305`); S3 afterwards. **V** |
| Rollup | Advisory transaction lock for the SQL only (`rollup.py:81-99`); emails after commit. **V** |
| Purge | One transaction for every Organisation (`retention/service.py:86-107`). **V** |

No session-level advisory locks anywhere (only `pg_advisory_xact_lock`, `rollup.py:82`). **V**

### F. Concurrency of duplicates

Covered in the table. The details that matter:

- Ingestion: safe today. Once anything can put PROCESSING back to QUEUED while the first copy is
  still alive (a sweeper with a false positive), the final transaction has no ownership check
  (`pipeline.py:314-352`): both copies write, and for a staged edition the second raises
  `NoResultFound` in `_swap` (`:387`). The claim needs a fencing token; `attempt_count` is one. **V**/**I**
- Evaluation Run: safe (`job.py:387-391`). No unique constraint on
  `evaluation_case_results(run_id, side_id, run_case_id, repeat)` (`evaluation/models.py:288-315`);
  it only matters if Runs are ever resumed. **V**
- Live Verdict: unsafe, both pay and both record (D6). **V**
- Suggestion run: unsafe (D5). No unique constraint on `(suggestion_id, position)` for
  `suggestion_evidence`, `suggested_changes`, `suggestion_gaps` (`suggestions/models.py:144-212`). **V**
- Re-embed: data correct through `uq_chunks_position` (`documents/models.py:128-130`,
  `re_embedding/job.py:146`); the switch is safe because the second copy finds the job not running
  (`job.py:91-96,167-169`). Money wasted (D7). **V**
- Project delete, rollup, purge, clear alerts, delete objects: safe. **V**

### G. Money

| Paid call | Where | Recorded where | Retry pays twice? | Records twice? |
|---|---|---|---|---|
| Ingestion embeddings, active model | `pipeline.py:228` → `:182` | Nowhere (no usage row for embeddings) **V** | Yes: nothing is kept until the final transaction, so any re-run re-embeds the whole Document. Bounded today by 4 provider attempts. | n/a |
| Ingestion embeddings, pending model | `pipeline.py:236,256` | Nowhere **V** | Yes, as above | n/a |
| Re-embed embeddings | `re_embedding/job.py:253` | Nowhere **V** | Sequential: at most one batch (64 Chunks). Concurrent copies: every batch twice. | n/a |
| Run answers (chat, reranker, LLM classifier) | `job.py:285` → `:173-207` | `evaluation_case_results.cost_usd` (`:298`), committed with the answer (`:416`) **V** | A kill loses at most one paid answer and judgement, unrecorded. Re-run exits, so no double pay today. | No |
| Run judge | `job.py:318` | `judge_cost_usd` (`:330`) **V** | Same | No |
| Live Verdict judge | `live.py:196` | `live_verdicts.cost_usd` (`:226`) and `evaluation_spend.spent_usd` (`budget.py:134-141`) **V** | **Yes** on any second run | **Yes**: verdict Cost overwritten, spend added again. Kill after the call and before `:234`: paid, not recorded. |
| Proposer | `suggestions/service.py:833` | `suggestions.proposing_cost_usd`, overwritten (`:792-799`) **V** | **Yes** on any second run | No: pays twice, records once (the last call's Cost). Kill between `:833` and `:843`: paid, not recorded. |
| Suggestion check | inline `run_evaluation` (`service.py:879`) | `checking_cost_usd` = sum over the check's results, recomputed (`suggestion_check.py:101-115`, `service.py:774`) **V** | As a Run | No |

Not touched by any task: the Token Budget (a Redis counter incremented in the API,
`embed/api.py:341-342`; Runs create no Message, `job.py:7-9`), Trace cost on Messages, and usage
rollups (recomputed from raw rows, `rollup.py:27-39`). **V**

Provider calls carry no idempotency key, so "pays twice" can only be avoided by not making the
second call. **I**

### H. Object storage and other side effects

- `put` of converted markdown at a deterministic key, `<object_key>.converted.md`
  (`pipeline.py:86-88,210-214`, `storage/s3.py:86-93`): overwrite, idempotent. **V**
- `delete` and `delete_prefix`: idempotent (`storage/s3.py:116-134`). **V**
- Markdown written by an interrupted ingestion whose Document was then deleted: the delete lists
  `stored_keys` of the current and staged editions (`documents/service.py:632-634`,
  `pipeline.py:378-380`), which includes the markdown key, so nothing leaks there. **V**
- Unconfirmed uploads: the object exists in S3 while its pending record is in Redis
  (`documents/service.py:137-139`); if Redis loses it, the object stays until the Project is
  deleted. No lifecycle rule was looked for. **I**
- Audit events are written in the same transaction as the change they record
  (`re_embedding/job.py:186-194,210-217`, `projects/service.py:291-305`), so they are not
  duplicated by a re-run. **V**
- Emails: see D14.

### I. API-side background work that is not Celery

- No lifespan loops and no periodic work in the API (`app/main.py:117-173`). **V**
- `auth/account_api.py:94`: password-reset email through FastAPI `BackgroundTasks`; the token is
  committed and then the email sent (`auth/service.py:163-164`). A deploy or scale-in drops it;
  the user asks again. **V**
- `embed/api.py:338-351`: the reply that spends the Token Budget raises the alert and emails the
  Owners **inside the API process**, flag first (`embed/service.py:388-421`). Lost on a kill. **V**
- `embed/api.py:392-403`: after `yield done` the stream samples the reply and enqueues the Live
  Verdict. A client that disconnects on `done` closes the generator at that yield, so the reply is
  never sampled; that biases the sample towards clients that keep the stream open. **I** A process
  death between `live.py:106` and `embed/api.py:403` leaves PENDING forever. **V**
- `runtime/runtime.py:397`: a request-scoped pump task, cancelled in `finally`. Not job-like. **V**
- `tenancy/invites_api.py:126`: invite email sent in the request, failure reported to the caller.
  **V**
- A reply being streamed when the API task is stopped is lost to the Visitor. Not traced further. **I**

### J. Recovery and escape hatches today

| Job | Cancel | Retry | Delete | Works on a stuck row? |
|---|---|---|---|---|
| Document QUEUED / PROCESSING | none | refused, `DocumentBusyError` (`documents/service.py:331-334`) | allowed, no status guard (`:611-663`) | Only delete, then upload again. Replace is refused too (`:699-702`). **V** |
| Staged edition stuck | none | refused | delete the whole Document | Loses the Document's ID and Tags. **V** |
| Evaluation Run | `cancel_run` allows queued or running (`evaluation/service.py:981-1004`) | start a new one after cancel | no Run delete endpoint found | Yes, by cancel. **V** |
| Suggestion run | `cancel_suggestion` allows any in-progress status and cancels its check (`suggestions/service.py:353-380`) | start again | refused while in progress (`applying.py:254`) | Yes, by cancel. **V** |
| Suggestion's check Run | `cancel_run` has no kind filter (`evaluation/service.py:994-1004`) | | | Cancelling only the check leaves the Suggestion CHECKING if its task is dead. **V** |
| Live Verdict PENDING | none | none | none | No. It is only excluded from scores (`analytics/alerts.py:228`). **V** |
| Re-embed RUNNING | choose another model, or the active one (`projects/embedding.py:154-158`) | choose the model again | n/a | Yes; but choosing the **pending** model again "changes nothing" (`:149-150`), so the obvious retry does nothing. **V** |
| Project deletion | n/a | ask again (Project is still archived) | | Yes, if someone notices. **V** |

Studio: the Documents, Evaluation, Suggestions and Embedding views poll for as long as anything is
in progress (`frontend/apps/studio/src/projects/documents.ts:91-94`, `evaluation.ts:187-188`,
`suggestions.ts:57,74`, `embedding.ts:75`), with no timeout and no "taking longer than expected"
text (grep). Retry appears only once a Document is Ready or Failed
(`DocumentsTab.tsx:255-273`). A stuck row is a spinner for ever. **V** (shallow)

### K. Tests and conventions the fixes must respect

- Tasks run eagerly in the API process in tests: `CELERY_TASK_ALWAYS_EAGER=true`
  (`tests/conftest.py:50`), `task_eager_propagates=True` (`celery_app.py:41`). **V**
- Fakes at ports: object store `memory`, `FakeConverter` (with a `failure` hook,
  `documents/converter.py:78-90`), hash embedder, fake classifiers, fake model gateway, outbox
  mailer (`tests/conftest.py:52-61`); tests reach them through `app.state.ingestion` /
  `app.state.evaluation` (`documents/ports.py:5-7`). **V**
- Re-run tests call the task again directly:
  `await asyncio.to_thread(run_evaluation_task.apply, (run_id,))`
  (`tests/integration/test_evaluation.py:629-643`), `run_cascade` again
  (`test_project_deletion.py:294-303`). Interrupted states can be built the same way: set the row's
  status with SQL, then call the task or the sweeper. **V**
- A real worker is started only for the health probe, with `start_worker(pool="solo")`
  (`tests/integration/test_worker_health.py:48,71`). **V**
- `tests/integration/test_worker_entrypoint.py:33-47` asserts the Beat schedule and the `include`
  list; a new sweeper entry and any new task module must be added there. **V**
- Coverage gate: `fail_under = 100`, `branch = true` (`pyproject.toml:82-95`); ADR-0008
  (`docs/adr/0008-full-line-and-branch-coverage.md`): "Don't add ad-hoc `pragma: no cover`; write
  the test or change the design." Migrations are excluded and covered by an upgrade/downgrade
  round-trip. Every new branch (stale, not stale, cap reached, lost race) needs a test. There are 2
  existing pragmas, one at `suggestions/service.py:829`. **V**
- Migrations: Alembic, 61 revisions, named `YYYYMMDD_NNNN_slug.py` (`migrations/versions/`). **V**
- Where "worker interrupted" fits:
  - Document: status stays `failed`; `FailureCategory` has `unsupported_content`, `conversion`,
    `provider`, `quota` (`documents/models.py:53-63`). Either reuse `conversion` ("or something
    else went wrong while processing it") or add a fifth. GLOSSARY.md:291 and :307 would change:
    - "**Document status**: Where a Document is in ingestion: Queued (uploaded, waiting for the
      worker), Processing (being converted, chunked and embedded), Ready (its Chunks are stored and
      retrievable) or Failed (with a readable reason)."
    - "**Failure category**: What kind of failure set a Document to Failed, shown with its readable
      message: unsupported content (...), conversion error (the converter couldn't convert it, or
      processing went wrong), provider error (...) or quota (...)."
  - Evaluation Run: `RunStatus` is queued / running / completed / failed / cancelled
    (`evaluation/models.py:54-61`). Today **failed means "every answer errored"**
    (`job.py:22-23,421-423`; `CheckState.FAILED` "Every answer errored",
    `suggestion_check.py:45-46`), and finished Runs (completed or failed) feed "latest result"
    reads (`evaluation/service.py:331`). An interrupted Run has real, partial results, so reusing
    `failed` changes what those reads see. The glossary entry (GLOSSARY.md:861) names only: "An
    Editor starts it, an Agent has at most one in progress (queued or running), which an Editor can
    cancel (it stops between answers and keeps what it spent), and finished Runs are kept as its
    history". It has no sentence on failure; one would be added.
  - Suggestion run: `SuggestionStatus.FAILED` is commented "The Evaluation Model failed, timed out
    or gave invalid output" (`suggestions/models.py:36-37`). GLOSSARY.md:949: "It gathers the
    evidence, has the Evaluation Model propose the Suggestion and, when the Suggestion changes the
    configuration and the Agent has an Evaluation Set, checks it against the Live Version in an
    Evaluation Run. An Agent has at most one in progress, which an Editor can cancel". No failure
    sentence either.
  - Live Verdict: `LiveStatus.ERROR` "The Evaluation Model failed or timed out; left out of the
    Live score" (`evaluation/models.py:342-343`); GLOSSARY.md:909: "A reply the Evaluation Model
    couldn't judge has an Error instead."
  - Re-embed: GLOSSARY.md:261: "A failed Re-embed leaves the active model unchanged and shows why;
    choosing again while one runs cancels it."

## 3. Defects

Severity classes: **loses work**, **stuck forever**, **costs money**, **duplicates data**, **cosmetic**.

### D1. Commit-then-publish with nothing to reconcile (all producers)
- Evidence: the 11 call sites in section A; no sweeper anywhere. **V**
- Scenario: the API task is scaled in between `documents/service.py:273` and
  `documents/api.py:474`, or Redis refuses the publish. The Editor gets an error or nothing; the
  Document shows Queued for ever.
- Severity: stuck forever (Documents, Runs, Suggestions, Live Verdicts, Re-embeds); loses work
  (object and Project deletions).
- Smallest fix: a Beat sweeper that re-enqueues rows still QUEUED / PENDING after a threshold. Safe
  because each task claims atomically (after D6 and D5 are fixed).
- Migration: no for Documents, Runs, Suggestions and Live Verdicts (`updated_at` / `created_at`
  suffice for the queued state). Yes for deletions (D8, D9) and Re-embed (D7).

### D2. Broker loss orphans everything queued, unacked or counting down
- Evidence: single-node Redis (`infra/modules/cache/main.tf`); section B. **V**/**I**
- Scenario: ElastiCache restarts during a bulk upload; 40 Documents stay Queued, 3 stay
  "Retrying automatically".
- Severity: stuck forever.
- Smallest fix: the same sweeper as D1.
- Migration: as D1.

### D3. Ingestion killed mid-task is stuck in Processing
- Evidence: `pipeline.py:133-137,148,174`; `documents/service.py:331-334,699-702`. **V**
- Scenario: Spot reclaims the worker during Docling. The Document is Processing for ever; Retry
  and New edition answer 409; the same file uploaded again is refused as a Duplicate.
- Severity: stuck forever.
- Smallest fix: a claim that also takes over a stale PROCESSING row
  (`status = queued OR (status = processing AND updated_at < now() - ttl)`), a heartbeat that
  refreshes `updated_at` while the task runs, and an ownership check in the final transaction and
  in `_settle` (compare the `attempt_count` captured at claim).
- Migration: no (reuses `updated_at` and `attempt_count`).

### D4. Evaluation Run killed, or failing with any unhandled exception, is stuck Running
- Evidence: `job.py:386-427` (no `try`), `:388-391`; `evaluation/tasks.py:21-36`; blocking index
  `evaluation/models.py:190-195`; `evaluation/service.py:772-775`; `suggestions/service.py:249-252`. **V**
  One exception path that needs no kill: `session.get_one(ProviderCredential, run.judge_credential_id)`
  (`job.py:316`) with `judge_credential_id` set NULL by `ondelete="SET NULL"`
  (`evaluation/models.py:211-213`) if the credential is deleted mid-Run. Whether deletion is
  blocked while a Run uses it was not traced. **I**
- Scenario: scale-in kills a 40-minute Run at answer 300 of 1,200. The Run shows Running for ever;
  Evaluate and Suggest answer 409 until someone cancels it.
- Severity: stuck forever.
- Smallest fix: heartbeat column touched at each answer commit (`job.py:415-416`) and by a
  background beat; the sweeper marks stale Runs as interrupted; wrap the job so an unexpected
  exception ends the Run with a reason.
- Migration: yes (`evaluation_runs.heartbeat_at`, or `updated_at`).

### D5. Suggestion run: stuck on kill; a second run duplicates evidence, pays the proposer again and can wedge
- Evidence: `suggestions/service.py:563-575,813,622-656,833,843,740-760,686-692,803-880`;
  `evaluation/service.py:774-775`; no unique constraints `suggestions/models.py:144-212`. **V**
- Scenario (the untraced question from the first audit): the worker dies while the Suggestion is
  CHECKING. On redelivery `_set_status` moves it back to GATHERING, evidence rows are inserted a
  second time, the proposer is paid a second time, `_proposed` calls `start_check`, which raises
  `RunInProgressError` because the dead check Run is still RUNNING. That error is not in
  `_UNCHECKABLE`, so the task crashes. End state: Suggestion PROPOSING for ever with doubled
  evidence and an overwritten proposing Cost; check Run RUNNING for ever; the Agent blocked.
- Severity: stuck forever; costs money; duplicates data.
- Smallest fix: make the first transition a real claim (`WHERE status = 'queued'`), so a second
  delivery exits; heartbeat plus sweeper to mark stale runs failed and cancel their check
  (`stop_check`, `suggestion_check.py:92-98`); wrap the job as in D4.
- Migration: yes for the heartbeat column; unique `(suggestion_id, position)` on the three child
  tables is an optional backstop.

### D6. Live Verdict has no guard: double judge, double spend, and no way out of Pending
- Evidence: `evaluation/live.py:178-234`; `evaluation/budget.py:127-159`; no endpoint (section J). **V**
- Scenario: `acks_late` redelivers a verdict whose first run finished but was not acked. The judge
  is called again and `evaluation_spend.spent_usd` grows a second time; near the budget this pauses
  sampling early. Separately: a kill mid-judge leaves the verdict Pending for ever.
- Severity: costs money (pays twice and records twice); stuck forever.
- Smallest fix: return at the top unless PENDING; make the final write conditional
  (`UPDATE ... WHERE id = :id AND status = 'pending' RETURNING`) and call `add_spend` only when it
  hit. To stop the second paid call when two copies overlap, hold
  `pg_try_advisory_xact_lock` on the verdict ID across the judge call (a row lock would block the
  Purge, which is why the code locks late, `live.py:207-212`). Sweeper for old PENDING rows.
- Migration: no.

### D7. Re-embed: a lost message leaves the job Running for ever; concurrent copies pay twice
- Evidence: `projects/embedding.py:162-170`, `projects/embedding_api.py:169`,
  `re_embedding/tasks.py:47-49`, `re_embedding/job.py:171,236,253`, `re_embedding/models.py:27-63`,
  `pipeline.py:149-158,235-238`, `projects/embedding.py:149-150,227-243`. **V**
- Scenario: Redis restarts during the retry countdown. The job is RUNNING with no task. Every later
  upload is embedded with both models (paid twice per upload) indefinitely, the pending
  credential can't be deleted, and choosing the pending model again does nothing.
- Severity: stuck forever; costs money.
- Smallest fix: heartbeat column updated in `_step`; the sweeper re-enqueues a job whose heartbeat
  is stale (resumable, so restart is free); the task skips when the heartbeat is fresh and held by
  another copy (a lease), which also ends concurrent double embedding.
- Migration: yes (`re_embed_jobs.heartbeat_at`).

### D8. Project deletion: no record of the request, and an orphaned prefix after a mid-task kill
- Evidence: `projects/api.py:239-250`; `projects/service.py:263-272,285-306`;
  `projects/tasks.py:18-28`. **V**
- Scenario a: the message is lost; the Owner was told 202 and the Project stays archived.
- Scenario b: the worker dies after `service.py:305` and before `tasks.py:28`. The redelivered task
  finds no Project, gets `None` and deletes nothing. Every original file of a "permanently deleted"
  Project stays in S3.
- Severity: loses work; for b also a data-retention failure.
- Smallest fix: write the prefix to an object-deletion outbox row in the same transaction as the
  cascade, drained by the sweeper; record the request on the Project
  (`deletion_requested_at`, `deletion_requested_by`) in the API's transaction so a lost message is
  re-enqueued.
- Migration: yes (outbox table; two Project columns).

### D9. Object deletions are fire-and-forget
- Evidence: `documents/api.py:661-666,735-736`; `pipeline.py:355,361,429`;
  `documents/tasks.py:63-78`. **V**
- Scenario: an Editor deletes a Document holding personal data; the API task is replaced before the
  publish. The row is gone, the original and its markdown stay in S3 with nothing pointing at them.
- Severity: loses work (orphaned data that was meant to be deleted).
- Smallest fix: the same outbox table as D8: insert the keys in the transaction that removes the
  reference, publish as an optimisation, let the sweeper drain what is left.
- Migration: yes (shared with D8).

### D10. Automatic retries live only in the broker
- Evidence: `documents/tasks.py:52-54`; `pipeline.py:295-306,358-359,444-451`;
  `re_embedding/tasks.py:47-49`; `re_embedding/job.py:266-274`. **V**
- Scenario: the provider fails, `_requeue` commits QUEUED, the worker is killed before
  `apply_async` (early ack today), or Redis drops the countdown. Queued for ever, reading
  "Retrying automatically (attempt 2 of 4)".
- Severity: stuck forever.
- Smallest fix: covered by the D1 sweeper once the threshold is above the longest backoff (300 s,
  `core/settings.py:179`). Better: store `next_attempt_at` and the provider-attempt number on the
  row so the sweeper is the retry mechanism and the countdown message is only a shortcut.
- Migration: no for the sweeper-only fix; yes for the stored attempt.

### D11. With `acks_late`, the retry chain can fork
- Evidence: `documents/tasks.py:48-54` (attempt number travels in the message). **V**; the
  redelivery behaviour **I**.
- Scenario: attempt 1 publishes attempt 2 and is killed before its ack. Attempt 2 fails and
  schedules 3; the redelivered attempt 1 later claims the QUEUED row and schedules another 2. The
  Document gets more provider attempts than `ingestion_max_attempts`.
- Severity: costs money (bounded).
- Smallest fix: keep the provider-attempt number on the row (as D10).
- Migration: yes if done.

### D12. No time limit, no size limit and no attempt cap: poison jobs loop
- Evidence: section D. **V** / **V (celery src)**
- Scenario: a 48 MB scanned PDF with OCR on exhausts the 8 GiB task. With
  `task_reject_on_worker_lost` it is requeued at once and kills the next worker, for ever, taking
  the other slot's task with it each time.
- Severity: stuck forever; costs money (Fargate churn, repeated provider calls for the bystander).
- Smallest fix: cap at the claim (`attempt_count` since the last user action ≥ N → Failed);
  give Docling `document_timeout` and page limits; do not enable `task_reject_on_worker_lost`
  until the cap exists.
- Migration: no if `attempt_count` is reset on retry (`documents/service.py:342-345`); yes for a
  separate interruption counter.

### D13. The planned broker settings do not give the guarantee on their own
- Evidence: kombu `transport/redis.py:523-530,1070`; celery `worker/request.py:547-548,612-621`
  **V (celery src)**; Run size bound `evaluation/service.py:94`, `tenancy/models.py:70-71`. **V**
- Scenario a: visibility timeout 12 h. A killed ingestion is redelivered 12 h later.
- Scenario b: visibility timeout 1 h. A 3-hour Run's message is delivered again at 1 h, 2 h and
  3 h while it runs. Today the copies exit. If "a redelivered Run is marked failed" is how
  "worker interrupted" gets implemented, a healthy Run is failed at the one-hour mark.
- Scenario c: a hard time limit kills a task; the message is acked and the row is stuck.
- Severity: stuck forever / loses work, depending on the choice.
- Smallest fix: decide liveness from a DB heartbeat, never from "this message arrived again".
  Treat the broker as a wake-up call only.
- Migration: the heartbeat columns of D4, D5, D7.

### D14. Four alert emails are at-most-once, and a partial send is never completed
- Evidence (flag committed, then send):
  1. Token Budget exhausted: `embed/service.py:388-399` then `:412-421` (runs in the API). **V**
  2. Evaluation budget spent: `evaluation/budget.py:149-159` inside the judge transaction, commit
     `evaluation/live.py:234`, send `:235-242` → `budget.py:179-188`. **V**
  3. Block rate alert: `analytics/alerts.py:155-163` then `:164-166`. **V**
  4. Live score drop alert: `analytics/alerts.py:303-319` then `:320-322`. **V**
  Also at-most-once but user-retriable: password reset (`auth/service.py:163-164`,
  `auth/account_api.py:94`). Not affected: invites, sent in the request with the result reported
  (`tenancy/invites_api.py:122-135`). **V**
- Scenario: the rollup raises a Block rate alert, commits the flag, and the worker is killed before
  SES is called. The redelivered task sees the flag and sends nothing. Or: three Owners, the send
  to the first raises; the other two are never emailed.
- Severity: loses work (a lost alert).
- Smallest fix: record "emailed at" separately from "raised at" and send from a loop that picks up
  raised-but-not-emailed flags (the sweeper, or the next hourly run); that turns each into
  at-least-once with a small duplicate window.
- Migration: yes (one nullable timestamp per alert: two on `agents` for block rate and live score,
  one for the Token Budget; `evaluation_spend.budget_spent_emailed_at` would be split into
  reached/emailed).

### D15. Row locks held across the judge call in every Run
- Evidence: `job.py:247-251` (UPDATE), `:318` (judge), `:416` (commit). **V**
- Scenario: an Editor deletes a Document while a Run is judging a case that expects it; the delete
  waits up to the judge timeout (60 s) and may time out at the load balancer.
- Severity: cosmetic (latency), but it is the one place a task holds locks across a model call.
- Smallest fix: move the Stale-flag update after the judge call, next to the verdict inserts.
- Migration: no.

### D16. Beat ticks missed during a deploy or outage are skipped
- Evidence: section C. **V** / **V (celery src)**
- Scenario: a deploy stops Beat at 23:58 and the new task is up at 00:40. That day's Purge and
  budget-flag reset don't run; the hour's block-rate check is never made.
- Severity: loses work for a day (Purge one day late; a block-rate spike unreported); cosmetic for
  the badge.
- Smallest fix: make each task catch up by itself rather than persisting Beat's file: run the
  Purge hourly (it is idempotent and filters `purged_at IS NULL`); have the block-rate check cover
  "since the last check" by storing when it last ran.
- Migration: no for the Purge; yes for a last-checked timestamp.

### D17. Unhandled exceptions leave in-progress rows (no kill needed)
- Evidence: `job.py:386-427`, `suggestions/service.py:803-880`, `evaluation/live.py:178-242` have
  no catch-all, unlike ingestion (`pipeline.py:307-312`) and re-embed (`re_embedding/job.py:275-278`). **V**
- Scenario: a database hiccup on one commit in a Run raises; the task fails, is acked
  (`acks_on_failure_or_timeout`), and the Run is Running for ever.
- Severity: stuck forever.
- Smallest fix: one wrapper per job that ends the row with a readable reason; the sweeper is the
  backstop.
- Migration: no.

### D18. Every publish subscribes the API to a result nobody reads
- Evidence: celery `app/base.py:967-968`, `backends/redis.py:155-163,400-402`
  **V (celery src)**; no `ignore_result` in `app/`. **V**
- Scenario: the API process accumulates one pub/sub subscription per task it ever published, and
  the worker writes a result key per task.
- Severity: cosmetic (slow resource growth).
- Smallest fix: `task_ignore_result=True`, with `ignore_result=False` on `worker.health_check`.
- Migration: no.

### D19. One queue, two slots: long jobs starve short ones
- Evidence: `--concurrency=2`, no `task_routes` (`celery_app.py`, `infra/modules/ecs/main.tf:16`). **V**
- Scenario: two Runs occupy both slots for an hour. Uploads sit Queued, Live Verdicts sit Pending,
  the rollup and Purge wait. A staleness sweeper would then see "old QUEUED rows" and re-enqueue
  them again and again.
- Severity: cosmetic today; it becomes a correctness input once a sweeper exists (thresholds must
  not treat "waiting in a healthy queue" as lost, and re-enqueueing must be harmless).
- Smallest fix: two queues (long: Runs, Suggestions, Re-embed; short: the rest) and a worker
  service per queue; give sweeper re-enqueues a message `expires`.
- Migration: no.

### D20. Live Verdict sampling is skipped when the client closes on `done`
- Evidence: `embed/api.py:392-403`. **I**
- Severity: cosmetic (sample bias).
- Smallest fix: sample and enqueue before yielding `done`, or in a shielded step.
- Migration: no.

### D21. Ingestion's final write does not check it still owns the claim
- Evidence: `pipeline.py:314-352,387,415-427`. **V**; only reachable once something can re-queue a
  PROCESSING row. **I**
- Severity: duplicates data / wrong state, latent.
- Smallest fix: part of D3 (fencing by `attempt_count`).
- Migration: no.

### D22. Cancelling a Suggestion's check Run directly can strand the Suggestion
- Evidence: `evaluation/service.py:994-1004` (no kind filter). **V**
- Severity: stuck forever, only when the Suggestion's task is already dead; otherwise `_checked`
  completes it (`suggestions/service.py:764-778`).
- Smallest fix: covered by the D5 sweeper.
- Migration: no.

### D23. Budget badge depends on the midnight task
- Evidence: `agents/api.py:133`; `embed/service.py:392-394,424-435`. **V**
- Severity: cosmetic.
- Smallest fix: compute the badge as "flag is from today (UTC)"; the Beat task can then go.
- Migration: no.

### Verification of the first audit's claims

| Earlier finding | Result |
|---|---|
| `celery_app.py` sets none of the reliability options; `--concurrency=2`; no stopTimeout | Confirmed. **V** |
| `documents.ingest` stuck in PROCESSING; retry refused | Confirmed (D3). **V** |
| `evaluation.run` stuck RUNNING, blocks new Runs; no unique on case results | Confirmed (D4). It also blocks Suggestion runs. **V** |
| `evaluation.live_verdict` no guard, double `add_spend` | Confirmed (D6). **V** |
| `suggestions.run` not a claim; duplicates; untraced `start_check` | Confirmed, and traced: `RunInProgressError`, uncaught (D5). **V** |
| `projects.re_embed` resumable, concurrent copies pay twice | Confirmed (D7), plus the lost-message stuck state. **V** |
| `projects.delete` orphans the prefix | Confirmed (D8), plus: the request has no DB state. **V** |
| rollup, purge, clear alerts, delete objects, health check "safe" | Safe to run twice: confirmed. Not safe against loss: `delete_objects` (D9); alert emails (D14); missed ticks (D16). **V** |
| Emails never sent twice, so can be lost | Confirmed; four alert emails listed in D14. **V** |

## 4. Proposed design

### What the guarantee needs

1. A durable statement that a job was requested (survives Redis, API and worker death).
2. A way to tell "nobody is working on this" from "someone is".
3. A single place that acts on 2.
4. Each task safe to start twice.

Postgres already holds 1 for five of the seven job types (the status rows). The broker cannot
provide 2: on Redis, redelivery after a kill waits for the visibility timeout, and Runs can outlast
any timeout worth setting (D13).

### Options

**Option A: broker-centric.** `acks_late`, `reject_on_worker_lost`, long visibility timeout, and
per-task idempotency.
- Covers: worker death, eventually.
- Does not cover: the producer gap (D1), Redis loss (D2), lost countdowns (D10), hard time limits,
  poison loops (D12). Recovery time equals the visibility timeout. Needs every fix in D3 to D7
  anyway.

**Option B: database is the truth; one sweeper; the broker is a wake-up call.**
- Every job row carries `status`, a heartbeat timestamp and an attempt count. A task claims with
  one conditional `UPDATE` (queued, or in progress with a stale heartbeat), beats while it works,
  and checks it still owns the claim before its final write.
- One Beat task (every minute, also run once at worker start so it doesn't depend on Beat alone)
  applies a per-type policy to rows that are queued too long or whose heartbeat is stale, and
  drains a small outbox for the two side effects that have no row.
- Covers all of 1 to 4, including Redis loss and the producer gap, with one mechanism and one
  helper. Recovery time is the heartbeat TTL (minutes), independent of the broker.
- Cost: three heartbeat columns, one outbox table, two Project columns; a heartbeat helper.

**Option C: transactional outbox / Postgres job queue for everything.** A `jobs` table written in
the caller's transaction, a relay or `SKIP LOCKED` workers, leases and attempts on the job row.
- Covers everything and is generic for future jobs.
- Cost: duplicates state the domain tables already hold (two sources for "is this Run running"),
  replaces most of what Celery does, and is the largest change. Worth it only if Redis is to stop
  being the broker.

### Recommendation: Option B, with a narrow outbox

Mechanisms, in total:

1. **Claim with lease and fencing** (one helper). Claim:
   `UPDATE t SET status = <working>, heartbeat_at = now(), attempts = attempts + 1
   WHERE id = :id AND (status = <queued> OR (status IN <working> AND heartbeat_at < now() - :ttl))
   RETURNING attempts`. No row back → exit. A background asyncio task refreshes `heartbeat_at`
   every ~30 s (the event loop is free during Docling, which runs in a thread,
   `pipeline.py:200`). Final writes add `AND attempts = :mine`.
2. **One sweeper task** (`worker.sweep`, Beat every minute, plus on `worker_ready`), idempotent,
   under a `pg_advisory_xact_lock` like the rollup's.
3. **One outbox table** for object deletions (keys or a prefix), written in the transaction that
   removes the last reference.
4. **Catch-all wrappers** so an unexpected exception ends the row instead of leaving it.

Broker settings that fit this design:
- `worker_prefetch_multiplier=1`: yes.
- `task_acks_late=True`: acceptable once every task claims; it only shortens recovery after a clean
  shutdown. Keep the Redis visibility timeout at its default hour: duplicates of long tasks then
  arrive and exit on a fresh lease, and nothing waits on it for recovery.
- `task_reject_on_worker_lost=True`: only after the attempt cap exists (D12); the sweeper already
  recovers lost workers, with a cap.
- `task_ignore_result=True` except the health check (D18).
- ECS `stopTimeout=120` plus `REMAP_SIGTERM=SIGQUIT` and `worker_soft_shutdown_timeout≈100`, so
  short tasks finish and long ones are abandoned to the sweeper deliberately. (Requeue-on-cold-
  shutdown is **I**; the design does not depend on it.)
- Hard time limits only as a backstop above the lease logic, since a time-limited task is acked and
  relies on the sweeper.

What each job type needs:

| Job | Claim / guard | Sweeper policy | Schema |
|---|---|---|---|
| Ingestion | Claim in `_start` extended to stale PROCESSING; heartbeat on `updated_at`; fencing by `attempt_count` in the final transaction and `_settle` | QUEUED older than T (above the 300 s backoff) → re-enqueue. Stale PROCESSING → back to QUEUED and re-enqueue, until the cap; then Failed | None required. Optional: stored provider-attempt and `next_attempt_at` (D10, D11); new Failure category |
| Evaluation Run | Existing claim; heartbeat at each answer commit and from the background beat; catch-all wrapper | QUEUED too long → re-enqueue. Stale RUNNING → ended as interrupted, keeping answers and Cost | `heartbeat_at`. Unique `(run_id, side_id, run_case_id, repeat)` only if Runs are ever resumed |
| Suggestion run | First step becomes a claim from QUEUED only; heartbeat through all phases (the check's heartbeat counts); wrapper | QUEUED too long → re-enqueue. Stale in progress → Failed "worker interrupted", and `stop_check` on its check Run | `heartbeat_at`. Optional unique `(suggestion_id, position)` × 3 |
| Live Verdict | Exit unless PENDING; advisory try-lock across the judge call; conditional final update gates `add_spend` | PENDING older than a few minutes → re-enqueue up to N times, then Error (product decision) | None; optional `attempts` |
| Re-embed | Lease on the job row; heartbeat in `_step` | Stale RUNNING → re-enqueue (resumable); cap, then Failed through `_fail` | `heartbeat_at` |
| Project deletion | Request recorded on the Project; cascade inserts the prefix into the outbox in its transaction | Requested and still present after T → re-enqueue. Outbox rows → delete, then remove the row | `projects.deletion_requested_at/by`; outbox table |
| Object deletion | Keys inserted into the outbox in the deleting transaction | Drain | Outbox table |
| Rollup, Purge, clear alerts | Already safe twice | n/a. Make them self-catching-up (D16) | Optional alert "emailed at" columns (D14) |

Things the fixes must not do:
- Decide "interrupted" from a redelivered message (D13).
- Hold a row lock on a Live Verdict across the judge call (it would block the Purge).
- Re-enqueue without a claim that makes the extra message a no-op.
- Reuse Run `failed` for interrupted Runs without checking the reads that treat failed as "every
  answer errored" (section K).

Order of work that keeps each step shippable: D6 guard and D17 wrappers (no migration) → heartbeat
columns and claim helper → sweeper for queued and stale rows → outbox for deletions → attempt cap
and Docling limits → then turn on `acks_late` / Spot.

## 5. Open questions (product decisions)

1. **Attempt cap for ingestion.** How many interruptions before a Document is Failed rather than
   restarted? Does a user's Retry reset the count? Does it get its own Failure category?
2. **Staleness thresholds.** How long may a row be queued before it counts as lost (must exceed the
   300 s backoff and normal queueing under load), and how long without a heartbeat before a running
   job counts as dead? Shorter means faster recovery and more risk of a false positive.
3. **Interrupted Evaluation Run.** Is it `failed` with a reason, `cancelled`, or a new status?
   `failed` currently means every answer errored, and failed Runs feed "latest result". Should its
   partial results count for the Publish warning or the Evaluation summary?
4. **Interrupted Suggestion run.** Failed, as decided. If the proposer was already paid and the
   kill came during the check, should the proposed changes be kept as a completed, "not checked"
   Suggestion instead of being thrown away?
5. **Lost Live Verdict.** Re-judge automatically (free unless the first call was already paid) or
   mark Error? How many tries? Should a re-judge count against the Evaluation budget if the first
   attempt's Cost was never recorded?
6. **Lost alert emails.** Should a raised-but-unsent alert be sent late (possibly hours after the
   spike), and is a rare duplicate acceptable in exchange for never losing one?
7. **Missed hourly block-rate check.** Check the missed hours on catch-up, or accept the gap?
8. **Purge lateness.** Is a Purge up to a day late (missed 00:35 tick) acceptable for the Retention
   Window, or should it run hourly?
9. **Project deletion request.** Once deletion is requested, may the Project still be restored
   (today it can be until the task runs)? If the request is recorded, should the Studio show
   "Deleting"?
10. **Orphaned objects already in S3.** Is a one-off reconciliation (bucket listing against the
    database) wanted for objects orphaned before the outbox exists?
11. **Re-embed that keeps being interrupted.** Restart indefinitely (it is resumable and cheap), or
    fail after N interruptions and fall back to the active model?
12. **Stuck rows that exist now.** When the sweeper first runs it will find old QUEUED, PROCESSING,
    RUNNING and PENDING rows. Restart them, fail them, or only those younger than some age?
13. **Studio wording.** What does an Editor see for "restarted after an interruption" (Document)
    and "interrupted" (Run, Suggestion)? Should Retry be offered on a Document that has been
    Processing too long, as a manual escape hatch?
14. **Queue separation.** Is a second worker service (long jobs apart from short ones) acceptable
    cost-wise? Without it, thresholds in 2 must allow for hours of legitimate queueing.
15. **Worker memory versus upload size.** Lower the 50 MB cap or add page limits for OCR, or size
    the worker for the worst case?
