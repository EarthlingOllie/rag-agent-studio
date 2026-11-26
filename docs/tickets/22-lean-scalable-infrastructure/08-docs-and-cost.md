# 08: Docs and cost

**Ticket:** `22-08` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The documentation describes what now runs: the cost of leaving it on, how to show it scaling, and which parts of the scaled-up picture are built.

**Blocked by:**
- `22-05`

**Status:** done

- [x] The deploy guide's expected cost table is recomputed for the new shape, for always on and for one day, with the runs pool idle
- [x] The deploy guide gains a "showing it scale" section that says how to run the scaling script and what its timeline means
- [x] The README's architecture diagram, stack table and deploy summary show SQS and the two worker pools
- [x] The development guide describes the job queues and which jobs go to which
- [x] The infrastructure map's scaled-up view marks each row as a variable today or as future work, and its "decided" note links here
- [x] `make link-check` passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Seam: this ticket changes documentation only. The one behaviour it adds is that the development guide's table of jobs and queues must match the routing, checked by `backend/tests/unit/test_job_queue_docs.py` against the public `queue_for` and the tasks the Celery app registers (the same kind of contract as `tests/unit/test_aws_task_settings.py` checking `task-settings.json`). Every other criterion is prose, checked by `make link-check` and against the Terraform defaults.

TDD ([tdd-red.log](22-08-evidence/tdd-red.log)): the two tests were written first and failed because the guide had no "Which queue each job goes to" section; they pass with the table.

1. **Cost table recomputed for the new shape, always on and for one day, with the runs pool idle.** [deploy-demo.md, Expected cost](../../deploy-demo.md#expected-cost): one row per item at rest (general pool 1 Spot task, runs pool 0 tasks, API 1, Beat 1; no interface endpoints; SQS and the eight CloudWatch alarms added), about 0.17 USD an hour, about 120 USD a month always on (against about 240 before spec 22), about 4 USD for a day, plus what a running runs task, a migration, a seed and a scaling run add; the scaled-out (about 0.40 USD an hour) and without-Spot (about 175 a month) figures; and the assumptions (ARM64 Fargate unit prices, the Spot discount, alarm and SQS prices). Sizes and counts are the ecs module's `task_sizes`, `desired_counts` and `scaling` defaults; prices are published list prices, estimated offline (no AWS call). The README's cost line says the same.
2. **"Showing it scale" section.** [deploy-demo.md, Showing it scale](../../deploy-demo.md#showing-it-scale): what `scripts/deploy/scale.sh` (ticket 22-07) needs, what load it puts on each pool and the API, that its sizes and durations are arguments, that it deletes its Project, and how to read its timeline in four phases (load arrives, scale-out including the runs pool's cold start and the API's CPU target, drain under scale-in protection, scale-in after the idle alarm), its exit rule, and that ticket 22-09's real timeline is summarised there once it exists.
3. **README: architecture diagram, stack table and deploy summary show SQS and the two worker pools.** `README.md`: the diagram has the general and runs SQS queues, each feeding its own worker pool (Spot 1 to 3, Fargate 0 to 2), Beat feeding the general queue; the paragraph under it routes ingestion and Runs; the stack table says "a general and a runs queue" and lists the Spot pool, the runs pool scaling to zero, Application Auto Scaling and SQS; the deploy summary rolls the two pools (since 22-04) and gains a "Show it scale" step.
4. **The development guide describes the job queues and which jobs go to which.** [development.md, Which queue each job goes to](../../development.md#which-queue-each-job-goes-to): the two queues and their names locally and on AWS, which pool receives each on AWS and that one local worker serves both, and a table of all twelve Celery tasks with what each does, what sends it and its queue. The "Routing" bullet under "Jobs go through SQS" links to it. Tests: `test_the_guide_lists_every_job_the_worker_runs`, `test_the_guide_names_the_queue_each_job_is_routed_to`.
5. **Infrastructure map: scaled-up view rows marked, "decided" note links here.** [infra-simplification.md](../../infra-simplification.md#scale-out-view-same-terraform-different-variables): the diagram now shows the two SQS queues and pools; each row has a Status column, "Variable today" (with the ticket that built it) or "Future work" (with what it needs): `scaling.*`, `task_sizes`, `worker_spot`, `instance_class`/`multi_az`, `node_type`/`replicas` and `managed_nat` are variables today; a regular-Fargate base under Spot, read replicas or Aurora, three zones (the network module's validation allows exactly two), WAF and dead-letter notifications are future work. The "Decided" note links this ticket and the recomputed cost table, and says section 1 is the shape before spec 22.
6. **`make link-check` passes.** "Checked 3412 relative links in 386 Markdown files: all resolve."
7. **Highest seam, 100% coverage.** The new test adds no application code, so coverage is unchanged; it runs in the unit suite (2 passed). Ruff, ruff format and mypy clean. `make infra-check` was not rerun: nothing under `infra/` or `scripts/` changed.
8. **GLOSSARY / ADRs.** No new domain terms: queues, worker pools and autoscaling are runtime infrastructure, which the glossary does not cover (as for 22-03 to 22-06). No decision changed; ADR-0021 already states the shape these docs describe.

## Gaps and best guesses

- **Deferred (needs a live deploy, ticket 22-09):** the cost table is estimated from the Terraform defaults and published prices, not measured; the bill for a real day, the real scaling timeline (to be summarised in "Showing it scale"), the runs pool's cold start, and whether Fargate Spot capacity is offered for ARM64 tasks in `eu-west-2` (if not, `worker_spot = false` and the "without Spot" figure apply) are all ticket 22-09's evidence.
- **The Spot price** is taken as about 70% below on-demand, which is typical but varies; the spec's own estimate (Spot saving about 55 USD) assumes the same.
- **The scaling script was written in parallel (ticket 22-07).** The docs name it `scripts/deploy/scale.sh` and describe it from 22-07's criteria (Studio URL and Owner credentials, uploads, Evaluation Runs, API traffic, a timeline per poll, Project deleted, non-zero exit naming a service that never scaled out, sizes and durations as arguments) and from its in-progress use of the `deploy` output's queue names; the exact argument names are left to the script. When the two merge, check the name and the timeline's columns against the script.
- **SQS requests** are counted from Celery's long polling (about one receive per ten seconds for the one idle general worker) and Beat's sends: well under the free million a month, so under 1 USD in any case.
- **Section 1 of the infrastructure map** (the shape before spec 22, with its 240 USD) is kept as history rather than redrawn; the decided note says so and points to what runs now.
