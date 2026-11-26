# 01: Prefactor: one Job publisher port

**Ticket:** `21-01` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** Every background job is sent through one port, so a failed send no longer fails the request that queued it and tests can lose or hold a message. Nothing a Member sees changes.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] A Job publisher port with one operation per job the application queues today (ingestion, object deletion, Evaluation Run, Live Verdict, Suggestion run, Re-embed, Project deletion, the worker health probe); nothing else sends to Celery
- [ ] The production adapter sends to Celery exactly as today; the fake records what was sent and can be told to lose or hold the next message, and to release held ones
- [ ] A send that fails is logged with the job and its identifier and does not fail the request: the row is already committed and is the record (ADR-0020). The health probe is the exception and still reports the failure
- [ ] Jobs that queue follow-on work from inside a task (automatic retries, object deletions after ingestion) go through the same port
- [ ] Every job except the health probe ignores its result, so the API no longer subscribes to replies nobody reads
- [ ] The publisher fake is listed with the other ports in the shared test seams
- [ ] Existing behaviour is unchanged: the whole suite passes with no test rewritten to expect something different
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
