# 02: Queue module

**Ticket:** `22-02` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The demo environment gains two encrypted SQS queues, general and runs, each with a dead-letter queue and an alarm, and each service is allowed exactly the queue actions it needs. Nothing uses them yet.

**Blocked by:**
- None

**Status:** done

- [x] A queue module creates the general and runs queues, a dead-letter queue for each with a redrive limit, encryption at rest, and a CloudWatch alarm on each dead-letter queue's depth
- [x] Visibility timeouts are one hour on the general queue and twelve hours on the runs queue; both, and the redrive limit, are variables
- [x] Outputs: each queue's name, URL and ARN
- [x] The demo environment wires the module in and passes the queue names to the services as settings
- [x] Task roles: the API may send to both queues; the worker may receive from and send to both for now (22-04 narrows it per pool); Beat may send to the general queue only, its first policy
- [x] The deploy role may manage queues named for this project only
- [x] `terraform test` asserts the queues, dead-letter queues, encryption, alarms, outputs and each role's policy document
- [x] `make infra-check` passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Full table and logs: [22-02-evidence](22-02-evidence/README.md). [infra-check.log](22-02-evidence/infra-check.log): `make infra-check` green (queue module 14 runs, ecs 64, demo 8, bootstrap 9; TFLint clean; Checkov 332 passed, 0 failed).

## Gaps and best guesses

- **Deferred (needs a live deploy):** that the queues, alarms and policies behave as planned in a real account (a message really moves to the dead-letter queue after five receives, the alarm really fires, the deploy role can apply the module with its new statements) is proven only by ticket 22-09. Nothing here ran `terraform plan` against real state or `apply`.
- **SSE-SQS, not the data key:** "encryption at rest" uses SQS-managed keys. A customer key would need key-policy grants for every sender and receiver and adds KMS request costs, and messages carry only identifiers (ADR-0020).
- **Setting names:** `GENERAL_QUEUE_NAME`, `RUNS_QUEUE_NAME`, plus `GENERAL_QUEUE_URL` and `RUNS_QUEUE_URL` so the services never need `sqs:GetQueueUrl`. Every container gets them (the same rule as the database and cache parts: every process loads the same settings). The backend ignores them until 22-03 adds the settings; 22-03 may rename them on both sides together (`task-settings.json`).
- **Worker queue actions:** "receive" is `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility` and `GetQueueAttributes`, what a Celery SQS consumer needs on predefined queues. No `ListQueues` or `CreateQueue` anywhere.
- **Redrive limit 5, main queue retention 4 days (the SQS default), dead-letter retention 14 days:** the ticket names none of these; all but the dead-letter retention are variables.
- **Deploy role:** the policy lives in `infra/bootstrap` (the `ci-oidc` module takes it as `inline_policy_json`), so the test is there. "This project's names" is the existing `managed_resource_prefix` (`studio-`), the same rule as for IAM. An explicit deny on every other queue is what makes "only" true alongside `PowerUserAccess`. It takes effect when the bootstrap is re-applied by hand.
- **GLOSSARY:** no new domain terms. Queues and dead-letter queues are infrastructure, which the glossary does not cover. ADR-0021 already records the decision, and nothing here changes it.
