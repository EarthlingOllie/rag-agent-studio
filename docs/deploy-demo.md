# Demo environment: deploy, destroy and cost

`infra/envs/demo` composes every module in `infra/modules` (network, kms, database, cache, queue, storage, ecr, ecs, cdn) into one environment. The one module it does not compose is `ci-oidc`: the GitHub OIDC deploy role has to exist before CI can plan or apply anything, so `infra/bootstrap` owns it ([infra-bootstrap.md](infra-bootstrap.md)). `infra/tests/compose.test.sh` checks both.

Before the first deploy, apply the bootstrap and set the `AWS_DEPLOY_ROLE_ARN` secret and the `TF_STATE_BUCKET` variable ([infra-bootstrap.md](infra-bootstrap.md), steps 1 and 2). Create a GitHub environment called `demo` (Settings, Environments) if you want required reviewers on deploys and destroys; both workflows run in it.

## Deploy (bring the demo up)

Actions, **deploy**, Run workflow. Inputs:

- `image_tag`: the image tag to deploy. Leave it empty to build and deploy the commit you run the workflow on (its SHA). A tag that ECR already has (every merge to `main` pushes one) is deployed without rebuilding.
- `smoke_agent_id` (optional): the public ID of a live Agent. The smoke check then fetches that Agent's widget shell and expects 200. Empty checks an unknown Agent, which answers 404 with `frame-ancestors *`.

The job builds the Studio and widget (`pnpm build`), builds the images for `linux/arm64` if no tag was given, and runs [`scripts/deploy/deploy.sh`](../scripts/deploy/deploy.sh):

1. `terraform init` against the state bucket, then `terraform apply -target=module.ecr`, so that a first run creates the ECR repositories before pushing to them.
2. Push `rag-agent-studio/api` and `rag-agent-studio/studio` at the tag, unless ECR already has it. The job builds them for `linux/arm64` under QEMU, because the tasks run on ARM64 Fargate (ADR-0010); the script refuses to push an image of any other architecture. A tag that is neither in ECR nor built in the job fails here, before anything else changes.
3. `terraform apply -var=image_tag=<tag>`. This registers new task definitions for the API, the two worker pools, Beat and the migration task. It does **not** roll the services: they ignore task definition changes after creation (`lifecycle.ignore_changes` in the ecs module), so code never runs against an old schema.
4. Run the migration task (`alembic upgrade head`, its own least-privilege roles and security group, in the private subnets), wait for it to stop, and read its exit code. Anything but 0 stops the deploy; services keep running the old version.
5. Point each of the four services (`api`, `worker-general`, `worker-runs`, `beat`) at its new task definition (`aws ecs update-service`). A worker protects its task from scale-in while it holds a job, and ECS does not stop a protected task, so old worker tasks finish their jobs while the new ones start: the script looks every 30 seconds for old worker tasks (not on the new task definition) that are still protected, for up to 30 minutes, then clears their protection (`aws ecs update-task-protection --no-protection-enabled`) so the roll completes; a job cut short there is restarted or ended by the sweeper as after any interruption. The limit is the script's second argument (`deploy.sh <tag> 10` waits 10 minutes, `0` not at all). Then it waits for each service in turn (`aws ecs wait services-stable`) and prints `<service> is stable`. A service that cannot stabilise is rolled back by its deployment circuit breaker, and the run fails naming it.
6. Upload the Studio build (`frontend/apps/studio/dist`) and the widget build (`frontend/apps/widget/dist`: `embed.js` and `widget/assets/`) to the static bucket with `aws s3 sync --delete`. Content-hashed files are cached for a year; `index.html`, `embed.js` and the unhashed `widget/assets/widget.js` are uploaded with `Cache-Control: no-cache`.
7. Invalidate `/`, `/index.html`, `/embed.js` and `/widget/assets/widget.js` and wait for the invalidation.
8. Smoke check the CloudFront URL with [`scripts/deploy/smoke.sh`](../scripts/deploy/smoke.sh): `GET /api/health` answers 200 with `"status": "ok"`, `GET /` is the Studio's `index.html`, a deep link (`GET /projects`) is the Studio's `index.html` too (the SPA fallback CloudFront Function), `GET /api/smoke-check-not-found` keeps the API's JSON 404, and `GET /widget/a/<id>` answers with a `Content-Security-Policy` containing `frame-ancestors`. Each check is retried 20 times, 15 seconds apart. The URL is printed and added to the job summary.

Deploys and destroys share the `demo-environment` concurrency group, so they never overlap.

To deploy from a laptop instead, with credentials for the account: build the frontend (`cd frontend && pnpm build`), then `TF_STATE_BUCKET=<state_bucket_name> AWS_REGION=eu-west-2 scripts/deploy/deploy.sh <tag>`. Run `make images IMAGE_TAG=<tag> IMAGE_PLATFORM=linux/arm64` first if the tag is not in ECR yet (on an x86 machine this needs QEMU binfmt support, as Docker Desktop has).

`terraform output` in `infra/envs/demo` gives:

| Output | What it is |
|---|---|
| `cloudfront_url` | The public HTTPS URL of the Studio, widget and API |
| `bedrock_trust_principal` | The API task role ARN: the principal an Organisation trusts, with its external ID, in its Bedrock role (spec 02) |
| `ecr_repository_urls` | Where images are pushed |
| `deploy` | What `deploy.sh` and `seed.sh` read: cluster, services, task definitions, migration task, seed task, static bucket, distribution, URL |

The GitHub deploy role ARN (the principal GitHub Actions assumes) is the bootstrap's `deploy_role_arn` output.

### What the tasks are given

The API, the two worker pools, Beat, the migration task and the seed task run the same backend image, and their settings are validated at start (`backend/app/core/settings.py`). The ecs module gives each container plain values as environment variables and secrets by reference to Secrets Manager:

| Container | Environment | Secrets |
|---|---|---|
| all six | `ENVIRONMENT`, `AWS_REGION`, `DATABASE_HOST/PORT/NAME/USER`, `DATABASE_TLS=true`, `REDIS_HOST/PORT`, `REDIS_TLS=true`, `GENERAL_QUEUE_NAME/URL`, `RUNS_QUEUE_NAME/URL` (the queue module's queues) | `LOCAL_KEY_WRAPPER_KEY` (signs widget tokens) |
| API, both worker pools and seed | `OBJECT_STORE=s3`, `OBJECT_STORE_BUCKET/REGION`, `KEY_WRAPPER=kms`, `KMS_KEY_ID` (the credentials key), `STUDIO_URL` and `PUBLIC_BASE_URL` (both the CloudFront URL, which serves the API; ElevenLabs reaches the turn endpoint for Calls at the second) | `DATABASE_PASSWORD`, `REDIS_AUTH_TOKEN` |
| API only | `BEDROCK_PLATFORM_PRINCIPAL` (its own task role) | `SESSION_SECRET` |
| Beat | | `REDIS_AUTH_TOKEN` |
| migration | | `DATABASE_PASSWORD` |
| seed | | `SESSION_SECRET` (it runs the API in process) |

The settings build `DATABASE_URL` (`postgresql+asyncpg://…?ssl=require`) and `REDIS_URL` (`rediss://…?ssl_cert_reqs=required`) from the parts. Beat and the migration task get the addresses they never connect to because every process loads the same settings. [`infra/modules/ecs/tests/task-settings.json`](../infra/modules/ecs/tests/task-settings.json) records this table; the ecs module's `terraform test` and the backend's `tests/unit/test_aws_task_settings.py` both check against it, so a change on either side that would stop the tasks starting fails a test. Bump the ecs module's `key_wrapper_secret_version` for a new `LOCAL_KEY_WRAPPER_KEY` (issued widget tokens stop working).

### Job queues

The queue module (ticket 22-02, [ADR-0021](adr/0021-sqs-two-worker-pools-autoscaling.md)) creates two standard SQS queues, `studio-demo-queue-general` and `studio-demo-queue-runs`, encrypted at rest with SSE-SQS. A received message stays hidden for an hour on general and twelve hours (the SQS maximum) on runs (`general_visibility_timeout_seconds`, `runs_visibility_timeout_seconds`). After five failed deliveries (`max_receive_count`) a message moves to the queue's dead-letter queue (`…-dlq`, kept 14 days), and the CloudWatch alarm `…-dlq-depth` goes into alarm while that queue holds anything. The alarms notify no one: look at them in the console. Since ticket 22-03 every job goes through them. The API and the seed task may send to both queues, each worker pool may receive only from its own queue and send to both, and Beat may send to the general queue only. Sending needs no KMS permission, because the queues use SSE-SQS.

### Worker pools

Since ticket 22-04 the worker is two ECS services on the one backend image, each started with `--queues=` its own queue ([ADR-0021](adr/0021-sqs-two-worker-pools-autoscaling.md)):

| Service | Queue and jobs | Capacity | Size (default) | Task role beyond the queues |
|---|---|---|---|---|
| `worker-general` | general: ingestion, Re-embeds, deletions, Live Verdicts, alert emails, the scheduled jobs and the sweeper | Fargate Spot (`worker_spot = false` moves it to regular Fargate) | 2 vCPU, 8 GB | the documents bucket and data key, decrypt with the credentials key |
| `worker-runs` | runs: Evaluation Runs and Suggestion runs | regular Fargate | 1 vCPU, 6 GB | decrypt with the credentials key |

The cluster has the `FARGATE` and `FARGATE_SPOT` capacity providers; every service other than the general pool uses `FARGATE`. ECS does not fall back from Spot to regular capacity by itself: during a Spot shortage ingestion waits until you set `worker_spot = false` in `infra/envs/demo` and deploy. Worker containers have a two-minute stop timeout (`stopTimeout = 120`, Fargate's most), so a short job finishes inside a Spot interruption warning. Both pools run two jobs at a time (`--concurrency=2`, the `jobs_per_task` of [autoscaling](#autoscaling)). The runs pool's 6 GB comes from a measurement: two worker processes with the local Embedding Model and the Guardrail classifier loaded peak at about 4.7 GB (ticket 22-04's evidence), more than the 4 GB first planned. Sizes are the ecs module's `task_sizes`. Ticket 23-01's spike measured the API process with its local models at about 2.33 GB, above the API's 1 GB task size ([memory](tickets/23-floci-rehearsal/01-spike-terraform-apply-on-floci.md#memory-and-a-worker-size-for-a-16-gb-laptop)); ticket 22-09 checks that on AWS. The database admits the API, both pools and the migration and seed tasks; the cache admits every service and the seed task.

### Autoscaling

Since ticket 22-05, Application Auto Scaling owns the task counts of the API and both worker pools ([ADR-0021](adr/0021-sqs-two-worker-pools-autoscaling.md)). Beat stays at one task.

| Service | Tasks (default) | Scales on |
|---|---|---|
| `api` | 1 to 3 | average CPU, target tracking at 60% |
| `worker-general` | 1 to 3 | its queue's jobs, waiting plus in flight |
| `worker-runs` | 0 to 2 | its queue's jobs, waiting plus in flight |

A worker deletes a message only when its job ends, so a job being worked on stays in flight and counts. While a pool's queue holds any job, the alarm `…-<pool>-jobs` keeps the pool at one task per two jobs (the slots a task has), up to its maximum: the runs pool starts its first task as soon as a Run is queued, which takes a few minutes for a cold Fargate task. Once the queue has held no job for five minutes, the alarm `…-<pool>-idle` returns the pool to its minimum, zero for the runs pool. Every minimum, maximum, target, cooldown and the idle time is in the ecs module's `scaling` input. `desired_counts` only sets each service's count when Terraform creates it; afterwards Terraform ignores it, so an apply never undoes a scale-out. The deploy role may manage scaling only on ECS services, and change only this project's services (`studio-*`).

Since ticket 22-06 scaling in never stops a task in the middle of a job. While a worker holds a job it protects its own task through the ECS agent's task-protection endpoint, with an expiry five minutes ahead (`SCALE_IN_PROTECTION_MINUTES`) that each heartbeat pushes forward, and clears it when the job ends; ECS then picks an unprotected task to stop. If the worker dies, the protection lapses within five minutes. A failure to set or clear protection is logged and the job goes on. Each pool's task role may set protection only on this cluster's tasks carrying its own service's `Name` tag, and the agent's endpoint acts on the calling task alone; the deploy role may read and clear protection on `studio-*` clusters' tasks only.

## Seed (fill the demo with data)

An empty Studio shows nothing, so after a deploy, seed the demo with the same Demo Organisation `make seed` builds locally (spec 10 story 4; ticket 10-05):

1. Deploy first (above). The seed runs on the image the deploy applied, needs the migrations it ran, and relies on the general worker pool to ingest the demo Documents, which the seed queues on the general queue.
2. Actions, **seed**, Run workflow. Leave `reset` unticked to seed (or complete) the demo; tick it to erase the Demo Organisation, and only that one, and build it again, like `make seed-reset`.
3. Wait for the run: a fresh seed plays four weeks of Seeded history, which takes a few minutes. The run log and the job summary show the seed's output: the CloudFront URL, the demo Owner's and Editor's sign-in details, and the demo pages' address (`<cloudfront_url>/demo/`).
4. Sign in at the CloudFront URL as the demo Owner or Editor, or open `/demo/` to meet the Product FAQ as a Visitor.

Running it again is safe: the seed finds the Demo Organisation through the demo Owner's account, adds only what is missing, puts back what was changed, and never replays the history, so nothing is duplicated.

The job runs [`scripts/deploy/seed.sh`](../scripts/deploy/seed.sh), which applies nothing:

1. `terraform init` against the state bucket and `terraform output -json deploy`. An environment that is not deployed, or was deployed before the seed task existed, stops here with "run the deploy workflow first".
2. `aws ecs run-task` with the ecs module's seed task: `python -m app.seed` on the backend image (`--reset` as a container command override), in the private subnets with no public IP. The demo Documents are in the image at `/seed`: `make images` and `docker compose` pass the repository's `seed` folder as the `seed` build context.
3. `aws ecs wait tasks-stopped`, repeated up to `SEED_WAIT_ROUNDS` times (default 6, about an hour), then the `seed` container's exit code. Anything but 0 fails the run.
4. The task's log (`/ecs/studio-demo-ecs/seed`, stream `seed/seed/<task ID>`) is printed and added to the job summary.

The seed task has its own roles and security group. Its task role may use the documents bucket and the credentials key as the API's does (it uploads the demo Documents through presigned URLs and seals the demo credential), but not assume customer Bedrock roles. Its security group reaches HTTPS, Postgres and Redis, and the database and cache admit it. It runs 1 vCPU and 4 GB (`seed_task_size`), because it runs the API in process with the Guardrail classifier. The AWS seed always answers with the Demo model: a real credential would have to be passed as a run-task override, which ECS shows in the task's description, so add a real Provider Credential in the Studio instead.

From a laptop, with credentials for the account: `TF_STATE_BUCKET=<state_bucket_name> AWS_REGION=eu-west-2 scripts/deploy/seed.sh` (add `--reset` to erase and seed again).

Seeds, deploys and destroys share the `demo-environment` concurrency group, so they never overlap.

## Destroy (stop paying)

Actions, **destroy**, Run workflow, and type `destroy demo` into the confirmation. Anything else fails the run before it asks AWS for credentials, and nothing changes. The job runs [`scripts/deploy/destroy.sh`](../scripts/deploy/destroy.sh), which checks the confirmation again and runs `terraform destroy`. Buckets and ECR repositories are created with `force_destroy` / `force_delete`, and the ALB without deletion protection, so one run removes everything, including uploaded Documents and the database (RDS skips its final snapshot in the demo). The state bucket and the deploy role stay, so the next deploy works without re-bootstrapping.

From a laptop: `TF_STATE_BUCKET=<state_bucket_name> AWS_REGION=eu-west-2 scripts/deploy/destroy.sh "destroy demo"`.

## Showing it scale

Ticket 22-07's scaling script, `scripts/deploy/scale.sh`, lives with the deploy scripts. It needs a deployed and seeded demo (above), the CloudFront URL, the demo Owner's email and password, and, like `seed.sh`, the state bucket and AWS credentials: it reads the cluster, the services and the job queues from the `deploy` output and asks ECS and CloudWatch for task counts and queue depth. It creates a throwaway Project, uploads the seed Documents several times over under different names (general pool), starts Evaluation Runs on the seeded Agents (runs pool) and sends API requests for a few minutes (API). The load sizes and durations are arguments, with defaults that finish in about fifteen minutes. When it finishes, or is interrupted, it deletes its Project (and, if it failed or was interrupted, cancels its Runs), so it can be run again. AWS is only read, never changed.

```bash
OWNER_EMAIL=... OWNER_PASSWORD=... TF_STATE_BUCKET=<state_bucket_name> AWS_REGION=eu-west-2 \
  scripts/deploy/scale.sh <cloudfront_url>
```

Options: `--copies N` uploads of each seed Document (default 5), `--runs N` Evaluation Runs at most (default 3), `--api-seconds N` of load (default 300), `--api-workers N` parallel request loops (default 8), `--poll-seconds N` between timeline rows (default 30) and `--timeout-minutes N` before it gives up waiting for scale-in (default 25).

While it runs it prints a timeline, one line per poll: the time since it started, each queue's jobs (waiting plus in flight, the number the pools scale on) and each service's running tasks out of its desired count. Read it in four phases:

1. **Load arrives.** The general queue's jobs jump as the uploads are confirmed, and the runs queue's as the Runs start. Nothing has scaled yet: CloudWatch reports queue depth once a minute.
2. **Scale-out.** Within a minute or two of a queue holding jobs, its `…-jobs` alarm sets the pool's desired count to one task per two jobs, up to its maximum (3 for general, 2 for runs). The general pool's new tasks appear quickly; the runs pool goes from 0 to 1 and then 2, and its first task takes a few minutes to show as running, because a cold Fargate task pulls the multi-gigabyte backend image (the cold start the real-AWS run measures). The API's desired count follows its average CPU (target 60%) and rises after about three minutes of load.
3. **Drain.** The jobs fall to zero as the pools work through them. A pool does not shrink while a job is still in flight: in-flight jobs count, and a worker holding a job protects its task from scale-in ([autoscaling](#autoscaling)).
4. **Scale-in.** Five minutes after a queue last held a job, its `…-idle` alarm returns the pool to its minimum: the general pool to 1 and the runs pool to 0. The API drifts back to 1 more slowly, as target tracking scales in cautiously.

The script stops once every service is back at its minimum with both queues empty, or after `--timeout-minutes`. It exits non-zero, naming each service, if a pool or the API never scaled out (`Did not scale out`) or was not back at its minimum in time (`Did not scale in`). A timeline from a real run is evidence for ticket 22-09 ([prove it on real AWS](tickets/22-lean-scalable-infrastructure/09-prove-it-on-real-aws.md)), which summarises it here once it exists.

Only real AWS shows the pools scaling on their own alarms. Ticket 23-01's spike on the Floci emulator ([findings](tickets/23-floci-rehearsal/research/floci-findings.md#spike-results-ticket-23-01-2026-11-27)) found that Floci never evaluates metric-math alarms, which the pools' `…-jobs` and `…-idle` alarms are, and returns nothing for the same `GetMetricData` queries the script uses for its queue columns; it publishes no ECS CPU metric either. Ticket 23-05 also found that it does not run a step policy on an alarm state set by hand, and that it answers those `GetMetricData` queries with zeros, so the rehearsal's queue columns read `0+0`. So `make rehearse-scale` ([23-05](tickets/23-floci-rehearsal/05-make-rehearse-scale.md)) runs this same script on the seeded rehearsal while `scripts/deploy/rehearsal/drive-scaling.sh` publishes each pool's queue jobs (waiting plus in flight) as `Rehearsal/SQS` `Jobs`, the single metric the pools' alarms watch in `infra/envs/local` (the ecs module's `jobs_metric_namespace`), and the API tasks' CPU measured with `docker stats` as `AWS/ECS` `CPUUtilization`. Floci then evaluates those plain alarms and runs the same step and target-tracking policies. The rehearsal caps the API and the general pool at 2 tasks and the runs pool at 1, with 30-second cooldowns and a one-minute idle time, so it fits a 16 GB laptop; the pools are back within a few minutes, and the API last, after Floci's target tracking has seen fifteen low minutes.

## Rehearse it on Floci (no AWS account)

Spec 23's rehearsal applies the same modules to Floci, an AWS emulator ([findings](tickets/23-floci-rehearsal/research/floci-findings.md)), through `infra/envs/local`, then runs the unchanged deploy, seed and scaling scripts against it. Use it before a real deploy, after any change under `infra/` or `scripts/deploy/`.

**Prerequisites.** Docker with access to its socket (Floci starts the database, cache, registry and tasks as containers; on Linux add yourself to the `docker` group or set `DOCKER_HOST`) and at least 8 GB of memory for Docker, about 16 GB in the machine for a scaled-out rehearsal; `jq`, `curl`, and Node with pnpm for the frontend build. Terraform and the AWS CLI are not needed: they run in containers on a network that reaches only Floci, with dummy credentials, so no AWS account can be touched whatever credentials the machine holds. The rehearsal uses port 4566, so it stops `make dev`'s Floci first (`make services` starts it again). Floci pulls its images from Docker Hub, which limits anonymous pulls: `docker login`, or set `REHEARSAL_IMAGE_MIRROR=mirror.gcr.io`. It runs on x86_64 and Apple-silicon machines and builds the images for the machine's own architecture.

**Commands.**

| Command | What it does |
|---|---|
| `make rehearse` | Starts Floci and its front end, builds the images and the frontend, applies `infra/envs/local` through the unchanged `deploy.sh` (push, migrate, roll, upload, smoke check), then plans again and fails unless the plan shows no changes. Prints the Studio's address, `http://<id>.cloudfront.localhost:4566` |
| `make rehearse-seed` | Seeds the demo Organisation as a one-off task (`REHEARSAL_SEED_ARGS=--reset` to start again); sign in as `owner@northwind.example` / `northwind-owner-demo` |
| `make rehearse-scale` | Runs the [scaling script](#showing-it-scale) on the seeded rehearsal with a laptop-sized load and prints its timeline; fails naming a service that never scaled (`REHEARSAL_SCALE_ARGS` passes its options) |
| `make rehearse-down` | Destroys the environment and removes Floci, the containers it started and its data |

On GitHub, Actions, **rehearsal**, Run workflow runs `make rehearse`, `make rehearse-seed` (and, if ticked, `make rehearse-scale`), then `make rehearse-down`, and uploads every log as the `rehearsal-logs` artifact. Run it by hand on the branch of a pull request that changes the infrastructure; it is not a required check. It logs in to Docker Hub when the `DOCKERHUB_USERNAME` variable and `DOCKERHUB_TOKEN` secret are set, and pulls through `mirror.gcr.io` otherwise. GitHub's standard Linux runner has the 16 GB it needs for public repositories; a private repository's smaller runner fails the memory check.

**What the rehearsal proves.** That the modules apply cleanly from nothing and a second plan shows no changes; that the deploy script pushes, migrates, rolls and uploads, and the smoke check passes through the distribution (health, the Studio, a deep link, an API 404 and the widget shell); that the tasks reach the queue, database, cache, bucket and key service by the addresses Terraform gave them (a Document uploaded through a presigned link becomes Ready); that the seed runs as a one-off task; that the API's CORS, Studio URL and trusted-proxy settings work behind the distribution; and that the scaling policies move each service out and back in when their alarms fire, the runs pool from zero.

**What only AWS proves** ([22-09](tickets/22-lean-scalable-infrastructure/09-prove-it-on-real-aws.md)):

- **IAM and security groups.** Floci does not enforce either, so a missing permission or rule passes here.
- **The CloudFront Function.** Floci stores it but does not run it; the rehearsal's front end (`infra/rehearsal/front`) runs the same file in front of Floci, so deep links work here without proving CloudFront runs it.
- **Spot interruptions.** Floci records `FARGATE_SPOT` but never reclaims a task.
- **Bedrock.** The rehearsal answers with the Demo model; nothing calls Bedrock.
- **ECS task protection through the agent.** Floci gives tasks no ECS agent endpoint, so a worker holding a job is not protected from scale-in; deploys and scale-in that wait for jobs are proved only on AWS.
- **The pools' metric-math alarms.** Floci never evaluates them; `local` swaps in a single published `Jobs` metric per queue (`jobs_metric_namespace`), and `make rehearse-scale` publishes it and the API's CPU itself. The alarms CloudWatch evaluates on AWS, ECS's own CPU metric and the timeline's queue columns are proved only there.
- **Sizes and cold starts.** Floci runs every task as a local container, with no image pull from a remote registry worth measuring; task sizes are the laptop's (`local` runs the API and workers at 3 GB), not the demo's.
- **The seed log's closing report.** `seed.sh` prints the first 10,000 events of the seed task's log, which can end before the sign-in report; the same happens on AWS.
- **TLS on the database, HTTPS at the edge and the real certificate.** Floci's database serves no TLS and its distribution plain HTTP.

## Expected cost

Rough list prices for `eu-west-2` (London), in USD, with the default variables, no free tier and almost no traffic, as of November 2026 (ticket 22-08 recomputed them from the Terraform defaults; nothing was measured on AWS). Treat them as an order of magnitude and check the [AWS Pricing Calculator](https://calculator.aws/) before relying on them: prices change and differ by region. The rows are the shape at rest: every scaled service at its minimum, so the runs pool is at zero tasks.

| Item | Sizing (default) | Per hour | Always on, per month (730 h) |
|---|---|---|---|
| Fargate Spot, `worker-general` | 1 task, 2 vCPU, 8 GB, ARM64; about 70% below on-demand (0.107) | about 0.032 | about 23 |
| Fargate, `worker-runs` | 0 tasks at rest (1 vCPU, 6 GB, ARM64: 0.062 per task-hour when running) | 0 | 0 |
| Fargate, `api` | 1 task, 0.5 vCPU, 1 GB, ARM64 | 0.023 | 17 |
| Fargate, `beat` | 1 task, 0.25 vCPU, 0.5 GB, ARM64 | 0.011 | 8 |
| Application Load Balancer | 1 ALB, minimal LCUs | 0.027 | 20 |
| RDS Postgres 16 | `db.t4g.micro`, single-AZ, 20 GB gp3 | 0.022 | 16 |
| ElastiCache Redis | `cache.t4g.micro`, 1 node | 0.018 | 13 |
| Public IPv4 addresses | ALB (2) and fck-nat (1); tasks have none | 0.015 | 11 |
| fck-nat | `t4g.nano` and its volume | 0.005 | 4 |
| KMS keys | 2 environment keys | 0.003 | 2 |
| Secrets Manager | 5 secrets (database master password, cache auth token, and the origin-header, session and key-wrapper secrets) | about 0.003 | about 2 |
| SQS and CloudWatch alarms | 2 queues and 2 dead-letter queues (an idle general worker's long polls, Beat's sends: well under a million requests a month); 8 alarms (2 dead-letter, 4 queue-depth, 2 API target tracking) | about 0.002 | about 1.5 |
| CloudFront, S3, ECR storage, CloudWatch Logs, NAT data | small at demo traffic | about 0.005 | about 3 |
| **Total** | | **about 0.17** | **about 120** |

- **Always on:** about 120 USD a month with the runs pool idle, against about 240 before spec 22. The four VPC interface endpoints (64 USD) are gone (ticket 22-01; ECR's API, Logs, Secrets Manager, SQS and KMS now go through `fck-nat`, and image layers still through the free S3 gateway endpoint), and Spot takes about 55 USD off the general pool (ticket 22-04).
- **Apply for a day:** about 4 USD for 24 hours at rest. Add 0.062 USD for each hour a runs-pool task runs (an Evaluation Run of half an hour costs about 3 cents of Fargate, plus its model calls, which the Organisation pays), a few cents for each migration task (0.25 vCPU for a minute or two) and each seed (1 vCPU and 4 GB for a few minutes, about 0.01 USD), and a few cents for a run of the [scaling script](#showing-it-scale) (fifteen minutes with up to two extra general tasks, two runs tasks and two extra API tasks). Destroy afterwards and the only remaining cost is the bootstrap's state bucket and key, about 1 USD a month ([infra-bootstrap.md](infra-bootstrap.md#cost)).
- **Scaled out:** with every scaled service at its maximum (3 API, 3 general, 2 runs tasks) Fargate costs about 0.30 USD an hour instead of 0.07, about 0.40 USD an hour in all. Autoscaling holds that only while the queues hold jobs or the API is busy.
- **Without Spot:** `worker_spot = false` puts the general pool on regular Fargate at 0.107 USD an hour, about 175 USD a month always on.
- **Cheaper:** every size, minimum and maximum is a variable (`task_sizes`, `scaling`). The general pool's minimum stays at one task, because it runs the sweeper and the scheduled jobs (ADR-0021).

Assumptions: Fargate ARM64 in `eu-west-2` at 0.03725 USD per vCPU-hour and 0.00409 USD per GB-hour (x86 less 20%); Fargate Spot about 70% below that, which is typical but varies by hour and availability, and assumes Spot capacity is offered for ARM64 tasks (ticket 22-09 checks this on AWS; if it is not, `worker_spot = false` gives the "without Spot" figure); a CloudWatch alarm at 0.10 USD a month per metric it reads (the queue-depth alarms read two); a Secrets Manager secret at 0.40 USD a month; SQS at 0.40 USD per million requests after the free million; data between tasks and AWS services in the region free except for crossing zones to the one `fck-nat`. The bill for a real day is evidence for ticket 22-09.
