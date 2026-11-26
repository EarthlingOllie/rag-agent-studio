# 03: Tracer: interrupted ingestion restarts

**Ticket:** `21-03` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A Document whose ingestion was cut short, or that was saved but never reached the queue, goes back to Queued and becomes Ready without anyone doing anything. This builds the claim, the heartbeat and the sweeper that every later ticket adds a policy to.

**Blocked by:**
- `21-01`

**Status:** ready-for-agent

- [ ] A job reliability module holds the claim, the heartbeat and the sweeper; a job type supplies only its policy (what counts as queued and in progress, and what to do with a stale row). Ingestion is its first job type
- [ ] Ingestion claims its row with one conditional update: a Queued row, or a Processing row whose heartbeat is stale. A job that can't claim exits without doing anything
- [ ] While it holds the claim, a job writes a heartbeat every 30 seconds, including during conversion and embedding
- [ ] The final write and the settle step check the job still holds the claim, so an older copy that is somehow still running can't write the Document
- [ ] A sweeper task runs every minute from Beat and once when a worker starts, under an advisory lock so two never overlap
- [ ] The sweeper re-sends a Document or staged edition that has been Queued for more than 15 minutes
- [ ] The sweeper returns a Processing Document or staged edition with no heartbeat for 5 minutes to Queued and re-sends it; the Studio shows it as Queued and then Ready
- [ ] A replaced Document whose new edition was interrupted is ingested again while its current edition keeps answering
- [ ] An ingestion that restarts leaves exactly one set of Chunks; a job delivered twice, or run as two copies at once, produces one result
- [ ] Documents already stuck on Processing or Queued when this ships are recovered by the first sweep
- [ ] The heartbeat interval, the dead-after time and the queued-too-long time are settings with the defaults above
- [ ] Each recovery is recorded in the traces with the job, its identifier and the reason
- [ ] Celery runs with a prefetch of one and late acknowledgement; requeue-on-worker-lost stays off
- [ ] The adapter fakes (converter, embedder, object store) gain a hook that aborts a job at a chosen point without running its error handling; tests use it with the controllable clock and call the sweeper directly
- [ ] The test that asserts the Beat schedule and the task list includes the sweeper
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
