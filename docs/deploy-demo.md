# Demo environment: deploy, destroy and cost

`infra/envs/demo` composes every module in `infra/modules` (network, kms, database, cache, storage, ecr, ecs, cdn) into one environment. The one module it does not compose is `ci-oidc`: the GitHub OIDC deploy role has to exist before CI can plan or apply anything, so `infra/bootstrap` owns it ([infra-bootstrap.md](infra-bootstrap.md)). `infra/tests/compose.test.sh` checks both.

Before the first deploy, apply the bootstrap and set the `AWS_DEPLOY_ROLE_ARN` secret and the `TF_STATE_BUCKET` variable ([infra-bootstrap.md](infra-bootstrap.md), steps 1 and 2). Create a GitHub environment called `demo` (Settings, Environments) if you want required reviewers on deploys and destroys; both workflows run in it.

## Deploy (bring the demo up)

Actions, **deploy**, Run workflow. Inputs:

- `image_tag`: the image tag to deploy. Leave it empty to build and deploy the commit you run the workflow on (its SHA). A tag that ECR already has (every merge to `main` pushes one) is deployed without rebuilding.
- `smoke_agent_id` (optional): the public ID of a live Agent. The smoke check then fetches that Agent's widget shell and expects 200. Empty checks an unknown Agent, which answers 404 with `frame-ancestors *`.

The job builds the Studio and widget (`pnpm build`), builds the images for `linux/arm64` if no tag was given, and runs [`scripts/deploy/deploy.sh`](../scripts/deploy/deploy.sh):

1. `terraform init` against the state bucket, then `terraform apply -target=module.ecr`, so that a first run creates the ECR repositories before pushing to them.
2. Push `rag-agent-studio/api` and `rag-agent-studio/studio` at the tag, unless ECR already has it. The job builds them for `linux/arm64` under QEMU, because the tasks run on ARM64 Fargate (ADR-0010); the script refuses to push an image of any other architecture. A tag that is neither in ECR nor built in the job fails here, before anything else changes.
3. `terraform apply -var=image_tag=<tag>`. This registers new task definitions for the API, worker, Beat and the migration task. It does **not** roll the services: they ignore task definition changes after creation (`lifecycle.ignore_changes` in the ecs module), so code never runs against an old schema.
4. Run the migration task (`alembic upgrade head`, its own least-privilege roles and security group, in the private subnets), wait for it to stop, and read its exit code. Anything but 0 stops the deploy; services keep running the old version.
5. Point each service at its new task definition (`aws ecs update-service`) and wait until all three are stable (`aws ecs wait services-stable`). A service that cannot stabilise is rolled back by its deployment circuit breaker, and the run fails.
6. Upload the Studio build (`frontend/apps/studio/dist`) and the widget build (`frontend/apps/widget/dist`: `embed.js` and `widget/assets/`) to the static bucket with `aws s3 sync --delete`. Content-hashed files are cached for a year; `index.html`, `embed.js` and the unhashed `widget/assets/widget.js` are uploaded with `Cache-Control: no-cache`.
7. Invalidate `/`, `/index.html`, `/embed.js` and `/widget/assets/widget.js` and wait for the invalidation.
8. Smoke check the CloudFront URL with [`scripts/deploy/smoke.sh`](../scripts/deploy/smoke.sh): `GET /api/health` answers 200 with `"status": "ok"`, `GET /` is the Studio's `index.html`, and `GET /widget/a/<id>` answers with a `Content-Security-Policy` containing `frame-ancestors`. Each check is retried 20 times, 15 seconds apart. The URL is printed and added to the job summary.

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

The API, worker, Beat, migration task and seed task run the same backend image, and their settings are validated at start (`backend/app/core/settings.py`). The ecs module gives each container plain values as environment variables and secrets by reference to Secrets Manager:

| Container | Environment | Secrets |
|---|---|---|
| all five | `ENVIRONMENT`, `AWS_REGION`, `DATABASE_HOST/PORT/NAME/USER`, `DATABASE_TLS=true`, `REDIS_HOST/PORT`, `REDIS_TLS=true` | `LOCAL_KEY_WRAPPER_KEY` (signs widget tokens) |
| API, worker and seed | `OBJECT_STORE=s3`, `OBJECT_STORE_BUCKET/REGION`, `KEY_WRAPPER=kms`, `KMS_KEY_ID` (the credentials key), `STUDIO_URL` (the CloudFront URL) | `DATABASE_PASSWORD`, `REDIS_AUTH_TOKEN` |
| API only | `BEDROCK_PLATFORM_PRINCIPAL` (its own task role) | `SESSION_SECRET` |
| Beat | | `REDIS_AUTH_TOKEN` |
| migration | | `DATABASE_PASSWORD` |
| seed | | `SESSION_SECRET` (it runs the API in process) |

The settings build `DATABASE_URL` (`postgresql+asyncpg://…?ssl=require`) and `REDIS_URL` (`rediss://…?ssl_cert_reqs=required`) from the parts. Beat and the migration task get the addresses they never connect to because every process loads the same settings. [`infra/modules/ecs/tests/task-settings.json`](../infra/modules/ecs/tests/task-settings.json) records this table; the ecs module's `terraform test` and the backend's `tests/unit/test_aws_task_settings.py` both check against it, so a change on either side that would stop the tasks starting fails a test. Bump the ecs module's `key_wrapper_secret_version` for a new `LOCAL_KEY_WRAPPER_KEY` (issued widget tokens stop working).

## Seed (fill the demo with data)

An empty Studio shows nothing, so after a deploy, seed the demo with the same Demo Organisation `make seed` builds locally (spec 10 story 4; ticket 10-05):

1. Deploy first (above). The seed runs on the image the deploy applied, needs the migrations it ran, and relies on the worker service to ingest the demo Documents.
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

## Expected cost

Rough on-demand list prices for `eu-west-2` (London), in USD, with the default variables, no free tier and almost no traffic. Treat them as an order of magnitude and check the [AWS Pricing Calculator](https://calculator.aws/) before relying on them: prices change and differ by region.

| Item | Sizing (default) | Per hour | Always on, per month (730 h) |
|---|---|---|---|
| Fargate, worker | 2 vCPU, 8 GB, ARM64 | 0.107 | 78 |
| Fargate, API | 0.5 vCPU, 1 GB, ARM64 | 0.023 | 17 |
| Fargate, Beat | 0.25 vCPU, 0.5 GB, ARM64 | 0.011 | 8 |
| VPC interface endpoints | ECR API, ECR Docker, Logs, Secrets Manager, in 2 AZs (8 ENIs) | 0.088 | 64 |
| Application Load Balancer | 1 ALB, minimal LCUs | 0.027 | 20 |
| RDS Postgres 16 | `db.t4g.micro`, single-AZ, 20 GB gp3 | 0.022 | 16 |
| ElastiCache Redis | `cache.t4g.micro`, 1 node | 0.018 | 13 |
| Public IPv4 addresses | ALB (2) and fck-nat (1) | 0.015 | 11 |
| fck-nat | `t4g.nano` and its volume | 0.005 | 4 |
| KMS keys | 2 environment keys | 0.003 | 2 |
| Secrets Manager | 4 secrets | 0.002 | 2 |
| CloudFront, S3, ECR storage, CloudWatch Logs, NAT data | small at demo traffic | about 0.005 | about 3 |
| **Total** | | **about 0.33** | **about 240** |

- **Always on:** about 240 USD a month. The worker (sized for Docling) and the interface endpoints are about 60% of it.
- **Apply for a day:** about 8 USD for 24 hours, plus a few cents for each migration task (0.25 vCPU for a minute or two) and each seed (1 vCPU and 4 GB for a few minutes, about 0.01 USD). Destroy afterwards and the only remaining cost is the bootstrap's state bucket and key, about 1 USD a month ([infra-bootstrap.md](infra-bootstrap.md#cost)).
- **Cheaper:** every size is a variable. Setting `desired_counts.worker = 0` between uses saves about 78 USD a month (no ingestion while it is 0). The endpoints could be dropped in favour of NAT traffic, at the price of slower image pulls through `fck-nat`.
