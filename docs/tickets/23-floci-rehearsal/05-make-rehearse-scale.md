# 05: `make rehearse-scale`

**Ticket:** `23-05` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** A developer watches both worker pools and the API scale out and back in on a laptop.

**Blocked by:**
- `23-04`

**Status: done.** Every criterion is met and evidenced below. Gaps and best guesses are listed at the end.

- [x] `make rehearse-scale` queues a batch of ingestion jobs and starts an Evaluation Run through the API of a seeded rehearsal
- [x] The general pool scales out and back on its queue's depth. 23-01 found the emulator publishes the queue metrics but never evaluates the pools' metric-math alarms, so the command drives those alarms from the queues' depth (`set-alarm-state`); check first that the emulator runs the step policy on a state set that way, and if not, add a module input that switches the pools' alarms to a single queue metric
- [x] The runs pool starts from zero for the Run and returns to zero
- [x] The command publishes a CPU figure for the API service to the emulator's CloudWatch and the API scales out and back
- [x] It prints the same timeline as the scaling demonstration script and exits non-zero if a service never scaled
- [x] `local` uses short cooldowns and a worker size that fits a 16 GB laptop (23-01 measured one job per task at 1 vCPU / 3 GB, about 8 GB for the whole stack)
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## How it was run

On 2026-11-27 in the x86_64 sandbox (4 vCPU, 15.7 GB, Docker 29.9.3), Floci 2.5.0, on the rehearsal 23-04 brought up (`make rehearse`, then `make rehearse-seed`), re-applied with this ticket's `local` inputs by a second `make rehearse` (12 resources changed in place: the scalable targets, the five policies and the four pool alarms; smoke check passed; the plan after the apply showed no changes). Terraform and the AWS CLI ran in containers on the rehearsal's tools network with dummy credentials, as in 23-03. Logs: [23-05-evidence](23-05-evidence/).

## Evidence

**Checked first: Floci does not run a step policy on an alarm state set by hand.** On the running Floci, a probe ECS service (0-3 tasks) got the pools' exact shape: an `ExactCapacity` step policy driven by a metric-math alarm. `set-alarm-state ALARM` (with `recentDatapoints: [3.0]` in the reason data) left the alarm in `ALARM`, but the service stayed at 0 desired for over a minute and `describe-scaling-activities` listed nothing. A plain alarm on a published metric (`put-metric-data` of `Rehearsal/Jobs` = 3) went `OK` then `ALARM` within 45 s, and the same step policy set the probe to 3 tasks, the step the value selects ([probe.log](23-05-evidence/probe.log)). So the ticket's fallback was taken.

**A module input that switches the pools' alarms to a single queue metric.** `infra/modules/ecs` gained `jobs_metric_namespace` (default null: unchanged metric math on `AWS/SQS`, as on AWS). Set, each pool's `…-jobs` and `…-idle` alarms watch `<namespace>/Jobs` with the pool's queue as `QueueName`, Maximum over 60 s, and nothing else changes (thresholds, missing-data rules, the policies they drive). Tests: `a_published_jobs_metric_replaces_the_metric_math_when_given`, `the_pools_alarms_use_metric_math_by_default`, `rejects_an_aws_namespace_for_the_jobs_metric`; every existing autoscaling run still passes, and the demo environment's tests are unchanged. New outputs `scaling` (the settings in effect) and `jobs_metric_namespace`.

**`make rehearse-scale`.** `rehearse.sh scale [scale.sh options]` initialises the `local` backend, reads the `deploy` output and the `jobs_metric_namespace` output, starts `scripts/deploy/rehearsal/drive-scaling.sh` in the background, and runs the unchanged-in-behaviour `scripts/deploy/scale.sh` with the demo Owner's published sign-in and a laptop-sized load (4 copies of each seed Document, at most 1 Run, 240 s of requests from 8 loops, a row every 15 s, a 30-minute limit; options given win). The driver is stopped when the script ends, however it ends, and its warnings are printed. Tests: `rehearse.test.sh` `scale_runs_the_unchanged_scaling_script_on_the_seeded_rehearsal_with_laptop_sized_load`, `scale_publishes_the_figures_floci_does_not_compute_while_the_script_runs_and_stops_after`, `scale_passes_options_through_and_they_win_over_the_defaults`, `scale_fails_when_a_service_never_scaled`. The driver, every 15 s: each pool queue's `ApproximateNumberOfMessages` + `ApproximateNumberOfMessagesNotVisible` as `Rehearsal/SQS` `Jobs`; the API tasks' CPU, `docker stats` on the `floci-aws-ecs-<task id>-api` containers divided by each task's CPUs (`NanoCpus`), averaged, as `AWS/ECS` `CPUUtilization` for the cluster and service (`drive-scaling.test.sh`: 8 cases, including no CPU when no API task runs, a failed publish reported and retried, the queue URLs looked up once).

**One fix in `scale.sh`.** Its first rehearsal run stopped at "creating the Project answered 401": the API's session cookie is `Secure`, and curl neither stores nor sends a Secure cookie over plain HTTP to a `*.localhost` name (browsers do). `scale.sh` now keeps the session cookie itself, from the latest `Set-Cookie: studio_session=…`, and sends it on every call and in the traffic loops; on AWS (HTTPS) nothing changes. Tests: `keeps_a_secure_session_cookie_over_plain_http` (the fake Studio on `e1.cloudfront.localhost`; red before the fix), `follows_a_renewed_session_cookie`, and the existing 36 cases.

**The run** ([scale.log](23-05-evidence/scale.log), [scaling-activities.log](23-05-evidence/scaling-activities.log)): 16 Documents uploaded and one Evaluation Run started on the HR helper (the other seeded Agents have no Evaluation Set).

Rows where something changed (all 64 rows are in scale.log):

```
time      elapsed  general queue  runs queue  api    worker-general  worker-runs
15:56:47  00:00    0+0            0+0         1/1    1/1             0/0
15:58:16  01:15    0+0            0+0         1/1    1/2             0/1
15:58:35  01:30    0+0            0+0         1/1    2/2             1/1
15:59:10  02:00    0+0            0+0         1/2    2/1             1/1
15:59:28  02:15    0+0            0+0         2/2    1/1             1/1
16:00:22  03:00    0+0            0+0         2/2    1/1             0/0
16:05:16  07:15    11+1           1+0         2/2    1/1             0/0
16:06:09  08:00    1+1            1+0         2/2    1/1             0/0
16:07:03  08:45    0+0            0+0         2/2    1/1             0/0
16:15:11  15:30    0+0            0+0         2/1    1/1             0/0
16:15:28  15:45    0+0            0+0         1/1    1/1             0/0

11731 API requests sent; 1 Evaluation Runs started.
Every service scaled out and back to its minimum: api 1 -> 2 -> 1, worker-general 1 -> 2 -> 1, worker-runs 0 -> 1 -> 0.
```

- **The general pool scaled out and back on its queue's depth:** the driver published 12 jobs for the general queue at 15:57; at 15:58:08 Floci set the pool to 2 tasks (2 running at 15:58:35), and back to 1 at 15:59:08 once the queue was empty.
- **The runs pool started from zero for the Run and returned to zero:** 1 job on the runs queue at 15:57-15:58; desired 1 at 15:58:08, running at 15:58:35; desired 0 at 16:00:08, a minute after the Run's job left the queue.
- **The API scaled out and back on the published CPU:** 76-103% of its half vCPU during the load; the target-tracking high alarm (3 periods above 60%) set 2 tasks at 15:59:08 (running at 15:59:28). After the load ended at about 16:01 the published CPU fell to 0; the low alarm (15 periods below 60%) set the API back to 1 task at 16:15:08 (1 running at 16:15:28).
- **The verdict:** "Every service scaled out and back to its minimum: api 1 -> 2 -> 1, worker-general 1 -> 2 -> 1, worker-runs 0 -> 1 -> 0", exit 0, after about 19 minutes (11,731 API requests); the throwaway Project was deleted. The script exits 1 naming any service that never scaled out or did not come back (`scale.test.sh`, unchanged cases).

**`local` scales at a laptop's size and pace.** API 1-2 tasks (cooldowns 30 s out, 60 s in), general pool 1-2 and runs pool 0-1 at one job per 1 vCPU / 3 GB task, 30 s cooldowns and a one-minute idle time (`local.tftest.hcl` `scales_like_the_demo_at_a_laptops_size_and_pace`; `fits_a_16_gb_laptop` unchanged). With every service scaled out the machine used at most 9.2 GB in all (Floci, its database, cache and registry, Beat, the API, two general tasks and the runs task; the runs task peaked at 2.5 GB, the general tasks at 2.7 GB), sampled every 20 s.

**Tests and coverage.** `make infra-check` passes ([infra-check.log](23-05-evidence/infra-check.log)). No backend or frontend code changed, so the 100% gate is unaffected.

**Glossary and ADRs.** No new domain term. ADR-0021 is unchanged (on AWS the pools still scale on metric math); spec 23's "Scaling helper" decision now records that the fallback was taken.

## Gaps and best guesses

- **The timeline's queue columns lag.** `scale.sh` reads Floci's own `AWS/SQS` metrics with `GetMetricData`; Floci answered zeros while the queues held jobs and reported the 15:57 depth (11+1 and 1+0) only from 16:05, about eight minutes late. The `Rehearsal/SQS` `Jobs` datapoints in [scaling-activities.log](23-05-evidence/scaling-activities.log) are the real depth, and they are what the alarms used. The late figures only delayed the script's "back at rest" check, not the verdict. Left as is: the columns are right on AWS.
- **The general pool's second task did little work.** Sixteen small Documents drained within about a minute, so the pool went 1 -> 2 -> 1 with the second task starting as the queue emptied. `--copies` raises the load (`REHEARSAL_SCALE_ARGS="--copies 8"`).
- **The API's scale-in follows Floci's target tracking:** its low alarm needs 15 periods below 60%, as AWS's does (AWS uses 54%), so the API is the last service back.
- **No task protection.** Floci has no ECS agent endpoint (23-01), so a busy worker could be stopped by scale-in here; on AWS task protection prevents it (22-06). Interrupted ingestion recovers through the sweeper (spec 21).
- **CPU from `docker stats`** is the container's share of the host, not ECS's metric; it is published only while `make rehearse-scale` runs, so outside it the API's high and low alarms see no data and the API stays where it is.
