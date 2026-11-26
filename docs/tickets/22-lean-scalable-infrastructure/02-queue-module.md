# 02: Queue module

**Ticket:** `22-02` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The demo environment gains two encrypted SQS queues, general and runs, each with a dead-letter queue and an alarm, and each service is allowed exactly the queue actions it needs. Nothing uses them yet.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] A queue module creates the general and runs queues, a dead-letter queue for each with a redrive limit, encryption at rest, and a CloudWatch alarm on each dead-letter queue's depth
- [ ] Visibility timeouts are one hour on the general queue and twelve hours on the runs queue; both, and the redrive limit, are variables
- [ ] Outputs: each queue's name, URL and ARN
- [ ] The demo environment wires the module in and passes the queue names to the services as settings
- [ ] Task roles: the API may send to both queues; the worker may receive from and send to both for now (22-04 narrows it per pool); Beat may send to the general queue only, its first policy
- [ ] The deploy role may manage queues named for this project only
- [ ] `terraform test` asserts the queues, dead-letter queues, encryption, alarms, outputs and each role's policy document
- [ ] `make infra-check` passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
