# Spec 22: Lean, scalable infrastructure

**Status:** ready-for-agent · **Builds on:** [Spec 09](./09-terraform-deploy-spec.md), [Spec 10](./10-seed-showcase-spec.md), [Spec 21](./21-job-reliability-spec.md) (must land first) · **Decisions:** [ADR-0021](../adr/0021-sqs-two-worker-pools-autoscaling.md), [ADR-0020](../adr/0020-database-is-the-record-of-jobs.md), [ADR-0010](../adr/0010-aws-runtime-shape.md), [ADR-0011](../adr/0011-single-cloudfront-origin.md) · **Background:** [current and simplified maps](../infra-simplification.md)

## Problem Statement

The AWS demo serves a handful of clients, yet it is an interview showcase and has to show that it scales. Today it does neither job well.

- It costs about 240 USD a month left on. A quarter of that is four VPC interface endpoints that only keep some traffic off the NAT, and a third is one worker sized for the largest document and running whether or not there is work.
- Nothing scales. Every service has a fixed task count, which spec 09 chose deliberately. A burst of uploads waits behind two worker slots, and a long Evaluation Run holds up ingestion for everyone.
- There is nothing to point at. A reviewer who asks "what happens under load?" gets a diagram, not a recording of the system adding and removing capacity.

## Solution

The same architecture, with the cost that doesn't help it scale removed, and real elasticity where the load is.

- **Workers follow the queue.** Jobs go through SQS. Two worker pools each scale on how many jobs are waiting: a general pool on Fargate Spot for work that restarts for free, and a runs pool on regular Fargate for Evaluation Runs and Suggestion runs, which scales to zero when there are none.
- **The API follows its load**, between one and three tasks.
- **Nothing in flight is cut short by scaling.** A worker holding a job is protected from scale-in, and a deploy waits for running jobs.
- **The network stays private and gets cheaper.** Tasks keep their private subnets; the four interface endpoints go.
- **It can be shown.** One script puts load on a deployed demo and records the pools growing and shrinking.
- **Local matches AWS.** `make dev` uses SQS too, through a Floci container.

Left on, the demo costs about half what it does today, and less when idle. The decisions are in [ADR-0021](../adr/0021-sqs-two-worker-pools-autoscaling.md).

## User Stories

### Queues

1. As a developer, I want jobs sent through SQS, so that queue depth is reported to CloudWatch without code of ours.
2. As a developer, I want two queues, general and runs, so that each kind of work is measured and scaled on its own.
3. As a developer, I want Evaluation Runs and Suggestion runs routed to the runs queue and every other job to the general queue, so that long paid jobs never wait behind ingestion or hold it up.
4. As a developer, I want each queue to have a dead-letter queue that takes a message after repeated failed deliveries, so that a message that can never be processed is set aside and visible.
5. As a developer, I want a CloudWatch alarm on each dead-letter queue, so that a set-aside message is noticed.
6. As a developer, I want the queues encrypted at rest and their messages to carry only identifiers, so that no customer content sits in a queue.
7. As a developer, I want Redis kept for sessions, sign-in throttling, rate limits, Token Budgets and the worker health probe, so that nothing but the job transport changes.
8. As a developer, I want the queues named by Terraform and given to the services as settings, so that tasks need no permission to create or list queues.

### Worker pools

9. As a developer, I want a general worker pool on Fargate Spot, so that work that restarts for free runs on the cheapest capacity.
10. As a developer, I want a variable that moves the general pool to regular Fargate, so that a Spot shortage is one change away from fixed.
11. As a developer, I want a runs worker pool on regular Fargate, so that paid jobs are interrupted only by deploys and failures.
12. As a developer, I want the general pool to keep at least one task, so that an upload starts at once and the scheduled jobs and sweeper always have a worker.
13. As a developer, I want the runs pool to scale to zero when its queue is empty, so that it costs nothing between Runs.
14. As an Editor, I want an Evaluation Run started while the runs pool is at zero to show as Queued and start within a couple of minutes, so that the wait is understood.
15. As a developer, I want each pool sized separately, with the runs pool smaller than the general pool, so that neither is paid for at the other's size.
16. As a developer, I want Beat kept as one fixed task, so that scheduled jobs are queued exactly once.
17. As a developer, I want workers given two minutes to stop, so that a short job finishes inside a Spot warning.

### Autoscaling

18. As a developer, I want each worker pool to scale out when jobs are waiting and in again when its queue is empty, counting jobs being worked on as well as jobs waiting, so that a pool never scales in under a running job.
19. As a developer, I want the API to scale between one and three tasks on CPU, so that request load adds capacity.
20. As a developer, I want every minimum, maximum and target to be a variable, so that the scaled-up shape is configuration.
21. As a developer, I want Terraform to leave task counts alone once autoscaling owns them, so that an apply doesn't undo a scale-out.
22. As a developer, I want a worker to protect its task from scale-in while it holds a job and release it when the job ends, including when it fails, so that scaling never interrupts work.
23. As a developer, I want the protection renewed while the job runs and to lapse by itself if the worker dies, so that a dead task is never protected for ever.

### Deploying

24. As a developer, I want a deploy to wait up to 30 minutes for running jobs before it stops them, so that a release doesn't interrupt an Evaluation Run that is nearly done.
25. As a developer, I want jobs still running after 30 minutes stopped and left to spec 21's recovery, so that one long Run can't block a release for hours.
26. As a developer, I want the deploy to roll both worker pools, the API and Beat, and to report each as stable, so that the workflow output is complete.
27. As a developer, I want the seed to queue its ingestion through SQS and wait for the general pool, so that seeding works unchanged.
28. As a developer, I want destroy to remove the queues with everything else, so that nothing new is left behind.
29. As a developer, I want the smoke check unchanged and still passing, so that the deploy is verified the same way.

### Network

30. As a developer, I want application tasks kept in private subnets with egress through `fck-nat`, so that no task has a public address.
31. As a developer, I want the four VPC interface endpoints removed and the S3 gateway endpoint kept, so that the demo stops paying for them while image layers still bypass the NAT.
32. As a developer, I want the managed-NAT toggle kept, so that a production-like network is still one change away.

### Permissions

33. As a developer, I want the API allowed only to send to both queues, so that it can queue jobs and do nothing else with them.
34. As a developer, I want each worker pool allowed to receive from its own queue and send to both, so that a job can queue follow-on work but can't read the other pool's jobs.
35. As a developer, I want Beat allowed only to send to the general queue, so that its first AWS permission is the smallest one.
36. As a developer, I want worker tasks allowed to set protection on themselves only, so that one task can't unprotect another.
37. As a developer, I want the deploy role allowed to manage queues, autoscaling and task protection in this project's names only, so that CI stays least-privilege.

### Local development and CI

38. As a developer, I want `make dev` to start a Floci container that provides SQS, with both queues created at start-up, so that the local stack uses the same transport as AWS.
39. As a developer, I want one local worker to serve both queues, so that the local stack gains no extra worker.
40. As a developer, I want the backend test suite to stay eager and broker-free apart from the one test that starts a real worker, so that tests don't slow down.
41. As a developer, I want that one test to run against Floci in CI, so that the real transport is exercised on every push.
42. As a developer, I want the end-to-end suite to pass on the compose stack with SQS, so that every user journey is proven on the new transport.

### Showing that it scales

43. As a developer, I want one script that uploads a batch of Documents and starts several Evaluation Runs against a deployed demo, so that both pools get real work.
44. As a developer, I want the script to send API traffic for a few minutes, so that the API scales too.
45. As a developer, I want the script to print a timeline of queue depth and running tasks per service, so that scale-out and scale-in can be read from its output.
46. As a developer, I want the timeline saved as evidence and summarised in the deploy guide, so that a reviewer can see it without an AWS account.
47. As a developer, I want the script to leave the demo as it found it (its Project deleted), so that it can be run again.

### Documentation and cost

48. As a developer, I want the expected cost table rewritten for the new shape, for always on and for one day, so that I know what leaving it up costs.
49. As a developer, I want the architecture diagram in the README and the development guide updated for SQS and the two pools, so that the docs match what runs.
50. As a developer, I want the "scaled" view kept in the infrastructure map with each row marked as a variable today or as future work, so that the scaling story is honest about what is built.
51. As a developer, I want spec 09's module tests updated where this spec replaces them, so that the old expectations don't fail.
52. As a developer, I want the whole change proven on real AWS once (deploy, seed, scaling script, destroy), so that Spot, autoscaling, task protection and the missing endpoints are known to work together.

## Implementation Decisions

- **What this replaces in spec 09.** The VPC interface endpoints (module boundaries, and the phrase "VPC endpoints for … ECR, Logs and Secrets Manager"). The fixed desired counts ("Autoscaling policies beyond a fixed desired count" under Out of Scope). The worker as one service at 2 vCPU / 8 GB in the cost defaults. Redis as the Celery broker. Everything else in spec 09 stands, including story 5 (private subnets and `fck-nat`), stories 14 and 15 (the Provider Credentials key and Secrets Manager) and the deploy order.
- **Queue module (new).** Two SQS queues, general and runs, each with a dead-letter queue and a redrive limit, encryption at rest, and an alarm on each dead-letter queue's depth. Outputs: names, URLs and ARNs. No notification target; the alarm is for the console.
- **Visibility timeouts.** Long enough that a normal job is not redelivered while it runs: one hour on the general queue, twelve hours (the SQS maximum) on the runs queue. A redelivered copy of a job that is still running fails its claim and exits (ADR-0020), so these are for tidiness, not for correctness.
- **Network module.** The interface endpoints and their security group are removed. The S3 gateway endpoint, the subnets, the `fck-nat` default and the managed-NAT toggle stay.
- **Compute module.** Services: `api`, `worker-general`, `worker-runs`, `beat`. Both worker services run the backend image with a queue argument. The cluster gains the Fargate and Fargate Spot capacity providers; `worker-general` uses Spot unless `worker_spot` is false. Worker tasks have a two-minute stop timeout. Desired counts are set at creation and then ignored.
- **Sizes (defaults, all variables).** `api` 0.5 vCPU / 1 GB, 1 to 3. `worker-general` 2 vCPU / 8 GB, 1 to 3. `worker-runs` 1 vCPU / 4 GB, 0 to 2, to be confirmed by measuring a Run's memory with the local Embedding Model and the Guardrail classifier loaded. `beat` 0.25 vCPU / 0.5 GB, 1.
- **Autoscaling.** Application Auto Scaling on the three scalable services.
  - `api`: target tracking on average CPU.
  - Workers: on the queue's waiting plus in-flight messages. `worker-runs` steps from zero to one when the sum is above zero and back when it has been zero for several minutes. Above one task, both pools track waiting messages per task against the slots a task has.
  - Cooldowns are short enough to show in a ten-minute demonstration and are variables.
- **Scale-in protection port.** A port with a production adapter that calls the ECS task-protection endpoint and a fake that records calls. The job reliability module (spec 21) sets protection when a job is claimed, renews it with the heartbeat and clears it when the job ends. Protection carries an expiry a few minutes ahead, so it lapses if the worker dies. Locally the adapter is a no-op.
- **Job publisher adapter.** The production adapter (spec 21's port) now publishes to SQS and routes by job type. The queue names come from settings. Celery uses predefined queues, so no task lists or creates queues.
- **Celery on SQS.** The retry backoff (at most five minutes) stays within what the transport supports. The health probe keeps its reply in Redis. Requeue-on-worker-lost stays off.
- **Task roles.** As in the Permissions stories. Workers also get the task-protection actions on their own task. Beat gets its first policy.
- **Deploy script.** Rolls `api`, both worker pools and `beat`. After starting the roll it waits up to 30 minutes for protected tasks to finish, then clears protection on the old tasks and lets the roll complete. The limit is an argument.
- **Deploy role.** Gains SQS, Application Auto Scaling and task-protection permissions scoped to the project's names.
- **Local stack.** A `floci` service in Compose, pinned to a version, used for SQS only, with storage kept between restarts. The API creates both queues at start-up when a setting says so, as it does for the bucket. RustFS and Mailpit stay as they are. One worker container serves both queues.
- **Settings.** The queue names and the AWS endpoint override for SQS are settings validated at start-up. There is no setting to fall back to Redis as the broker.
- **Scaling demonstration script.** Lives with the deploy scripts. It takes the Studio URL and Owner credentials, creates a throwaway Project, uploads the seed Documents several times over under different names, starts Evaluation Runs on the seeded Agents, sends API requests, polls ECS and CloudWatch, prints a timeline and deletes its Project. It needs a seeded demo.
- **Docs.** The cost table and a "showing it scale" section in the deploy guide, the README architecture diagram and stack table, the development guide's services and ports, and the status of each row in the infrastructure map.

## Testing Decisions

- **Good tests** assert each module's contract: given inputs, which resources exist with which security-relevant attributes, and which outputs are produced. They don't snapshot plans.
- **Module seam (`terraform test`, plan mode with mocked providers).**
  - queue: two queues, each with a dead-letter queue and a redrive limit; encryption on; the alarms; outputs.
  - network: no interface endpoints; the S3 gateway endpoint present; private subnets have no public IPs; the NAT toggle.
  - ecs: the four services and their commands; the Spot strategy and its off switch; the stop timeout; scalable targets with the given minimums and maximums; the runs pool's zero minimum; policies on the right metrics; desired count ignored; each task role's policy document (API send only, each pool receives only its own queue, Beat sends to general only, protection on self only).
  - ci-oidc: the deploy role's added permissions are limited to the project's names.
- **Static analysis** as in spec 09: `fmt`, `validate`, `tflint`, `checkov`, with any new skip justified inline.
- **Deploy script tests** (the existing Node test runner suite with a stubbed `aws`): the services rolled, the 30-minute wait, clearing protection after it, and the scaling script's timeline and clean-up.
- **Task seam with the Job publisher fake.** Each job type is published to the right queue.
- **Task seam with the Scale-in protection fake.** Protection is set on claim, renewed, and cleared when the job finishes, fails or is abandoned.
- **Real transport.** The test that starts a real worker runs against Floci's SQS. The end-to-end suite runs on the Compose stack with SQS. Prior art: that test today against Redis, and the end-to-end workflow.
- **Real AWS.** One manual run by the repository owner: deploy, seed, the scaling script, destroy. Its evidence records the timeline, the cold start of the runs pool, a Spot task being replaced if one happens, and the bill for the day. It is outside the coverage gate.

## Out of Scope

- Rehearsing the AWS deployment locally on Floci ([Spec 23](./23-floci-rehearsal-spec.md)).
- Scaling the general pool to zero.
- Read replicas, Aurora, a multi-AZ database or Redis replicas beyond the variables that exist.
- Moving application tasks to public subnets.
- Parameter Store in place of Secrets Manager, or one KMS key in place of two.
- Notifications from the dead-letter alarms.
- A WAF, a custom domain, or a second environment.
- Any change to job behaviour, which is spec 21's.

## Further Notes

- **Expected cost, to be recomputed in the deploy guide:** about 120 USD a month left on with the runs pool idle, against about 240 today. The interface endpoints account for about 64 of the saving and Spot for about 55.
- Fargate Spot can be unavailable. ECS does not fall back to regular capacity by itself; ingestion waits, or `worker_spot` is turned off.
- With no interface endpoints, ECR's API, CloudWatch Logs, Secrets Manager, SQS and KMS are reached through `fck-nat`, which is a single instance. That was already true of model providers and is accepted in ADR-0010.
- Cold start of the runs pool is dominated by pulling the backend image. The real-AWS run measures it; if it is long, a smaller image for the runs pool is a follow-up.
- ECS reports no CPU for a service at zero tasks, which is why the runs pool scales on its queue and not on load.
