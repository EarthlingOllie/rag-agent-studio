# 03: Jobs go through SQS

**Ticket:** `22-03` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** Locally and on AWS, background jobs are sent through SQS and routed to the general or runs queue. `make dev` gains a Floci container for SQS, and every user journey still passes.

**Blocked by:**
- `21-01`
- `21-02`
- `21-03`
- `21-04`
- `21-05`
- `21-06`
- `21-07`
- `21-08`
- `21-09`
- `21-10`
- `21-11`
- `21-12`
- `22-02`

**Status:** ready-for-agent

- [ ] The Job publisher's production adapter publishes to SQS: Evaluation Runs and Suggestion runs to the runs queue, every other job to the general queue
- [ ] Celery uses predefined queues named by settings, so no task lists or creates queues; the queue names and the SQS endpoint override are settings validated at start-up, with no fallback to Redis as the broker
- [ ] Redis still holds sessions, sign-in throttling, rate limits, Token Budgets and the health probe's reply
- [ ] `make dev` starts a pinned Floci container used for SQS only, with storage kept between restarts; the API creates both queues at start-up when a setting says so; one local worker serves both queues
- [ ] Automatic retries (at most five minutes) work on the SQS transport
- [ ] Messages carry identifiers only
- [ ] A task-seam test with the publisher fake asserts the queue each job type goes to
- [ ] The test that starts a real worker runs against Floci's SQS, and CI's backend workflow has Floci as a service
- [ ] The end-to-end suite passes on the Compose stack
- [ ] The development guide lists the new service, its port and the queue settings
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
