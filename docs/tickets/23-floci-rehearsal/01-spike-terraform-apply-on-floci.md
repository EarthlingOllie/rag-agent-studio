# 01: Spike: get `terraform apply` through on Floci

**Ticket:** `23-01` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** A throwaway run that applies the demo modules to Floci and records what really blocks it, so the rest of this spec is built on what the emulator does and not on what its source suggested.

**Blocked by:**
- `22-05`

**Status:** done

- [x] Floci runs with the Docker socket mounted and `terraform apply` of the demo modules reaches the end, with every workaround written down
- [x] Each of the research's nine blockers is marked confirmed, wrong or changed, with the fix that worked
- [x] Whether the emulator supports ECS task protection, Fargate Spot strategies and scaling on SQS queue depth is recorded
- [x] The memory the whole stack needs, and the worker size that fits a 16 GB laptop, are measured
- [x] Spec 23 and the research file are corrected where the emulator behaved differently; tickets 23-02 to 23-06 are adjusted if the spike changes their scope
- [x] No spike code is merged except the corrected documents
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## How the spike ran

Run on 2026-11-27 in the x86_64 sandbox (4 vCPU, 15.7 GB, Docker 29.9.3), Terraform 1.x with the AWS provider 6.72.0, against `floci/floci:2.5.0`. The logs are in [23-01-evidence](23-01-evidence/README.md).

- **No real AWS.** The sandbox can reach AWS hosts, so Terraform ran in a container on an internal Docker network (`docker network create --internal`) that Floci also joined: from there AWS hosts don't resolve and only Floci answers ([isolation.log](23-01-evidence/isolation.log)). Credentials were the dummy `test`/`test`; no AWS credential exists in the sandbox. `boto3` probes ran on the host against `http://localhost:4577` with the same dummy credentials.
- **Floci** ran with `docker run`, the Docker socket mounted, on its own bridge network `floci-spike` (172.29.0.0/16), with: `FLOCI_HOSTNAME=floci-spike`, `FLOCI_SERVICES_DOCKER_NETWORK=floci-spike`, `FLOCI_STORAGE_MODE=persistent` (named volume), `FLOCI_TLS_ENABLED=true`, `FLOCI_SERVICES_ECR_URI_STYLE=path`, `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:0.8.1-pg16`, `FLOCI_SERVICES_ELASTICACHE_DEFAULT_IMAGE=valkey/valkey:7.2`, `FLOCI_SERVICES_EC2_MANAGED_PREFIX_LIST_CATALOG_PATH` (a catalogue with the CloudFront list holding `127.0.0.0/8` and `172.29.0.0/16`), `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS=localhost`, `FLOCI_SERVICES_CLOUDFRONT_DOMAIN_SUFFIX=cloudfront.localhost`, `FLOCI_DEFAULT_REGION=eu-west-2`. `make dev`'s Floci already held host port 4566, so the spike's ran on `FLOCI_PORT=4577` (see the port finding below).
- **The environment** was a scratch copy of `infra/` with `envs/local` = `envs/demo` plus the provider and module changes listed under the blockers. State was in an S3 bucket in Floci with `use_lockfile = true`.
- **No app image.** The backend image (torch, Docling, bundled models) did not fit the sandbox's free disk next to its copy in Floci's registry, so the tasks ran an Alpine image with the commands overridden. The app's memory was measured on the host instead (see memory below).

## Evidence

### `terraform apply` reaches the end

Four rounds ([apply-rounds.log](23-01-evidence/apply-rounds.log)). Round 1 with the demo inputs unchanged failed on two module input validations, the fck-nat network interface, and hung on the S3 buckets' tags. Round 2 (S3 Control host resolvable) failed on the validations. Round 3 (`managed_nat = true`, the CDN origin set to `localhost`, the two validations widened) completed: all 171 resources of the demo composition exist in Floci. Round 4 changed the task definitions to `X86_64` and completed. `terraform destroy` then removed everything ([destroy.log](23-01-evidence/destroy.log)).

Every workaround the apply needed:

| Workaround | Why | Becomes |
|---|---|---|
| `AWS_ENDPOINT_URL`, dummy keys; provider `s3_use_path_style`, `skip_credentials_validation`, `skip_metadata_api_check`; backend `-backend-config=use_path_style=true -backend-config=skip_credentials_validation=true` | Blocker 1 | 23-03 provider and wrapper |
| The state bucket created first with `CreateBucket` and `LocationConstraint=eu-west-2` (a bare PUT is refused with `IllegalLocationConstraintException`) | Blocker 1 | 23-03 wrapper |
| The name `000000000000.<endpoint host>` must resolve to Floci (the spike used `--add-host`) | New: provider 6.x reads bucket tags through S3 Control, whose SDK prefixes the account ID to the endpoint host; unresolvable, the call retries for ever and the apply hangs | 23-03 wrapper |
| `managed_nat = true` | Blocker 9 (changed) | 23-03 `local` input (exists) |
| The CDN origin `localhost` and `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS=localhost` | Blocker 5 | 23-02 origin input |
| `image_repository_url` validation widened to Floci's path-style URI (`localhost:<port>/000000000000/<region>/<repo>`) | New: the ecs module refuses any non-ECR URL | 23-02 |
| `alb_dns_name` validation widened (Floci names the ALB `<name>-<16 hex>.elb.<FLOCI_HOSTNAME>`) | New: the cdn module refuses any name not ending `.elb.amazonaws.com`; with the origin input this validation moves to the origin | 23-02 |
| Task `cpu_architecture = "X86_64"` | Blocker 2 | 23-02 input |
| The prefix list catalogue file | Blocker 3 | 23-03 Compose file |
| pgvector and Valkey images pre-pulled from `mirror.gcr.io` and tagged with the names Floci asks for (also `registry:2`) | New: Docker Hub answered 429 Too Many Requests in the sandbox | 23-03 guide; 23-06 CI job |

### The research's nine blockers

| # | Blocker | Result | Fix that worked |
|---|---|---|---|
| 1 | No Floci endpoint config | **Confirmed**, plus the S3 Control host above | The provider, backend and wrapper settings above; `use_lockfile` worked (state and lock object in the Floci bucket; no lock left after an interrupted apply) |
| 2 | ARM64 tasks on an x86 host | **Confirmed**: Floci asks the daemon for `linux/arm64` and refuses an amd64 image ([ecs.log](23-01-evidence/ecs.log)) | `cpu_architecture = "X86_64"`: the task then ran |
| 3 | No CloudFront prefix list | **Confirmed**: empty without a catalogue ([prefix-list-and-ami.log](23-01-evidence/prefix-list-and-ami.log)) | The catalogue file; the reserved `com.amazonaws.` name is accepted (the research's inferred part holds) |
| 4 | deploy.sh pushes to real AWS | **Confirmed** by reading (deploy.sh was not run). With `ECR_URI_STYLE=path` the repository URL is `localhost:<port>/000000000000/eu-west-2/<repo>`; `docker push` over plain HTTP worked without a login, and the daemon pulled it for the tasks. No `*.localhost` HTTPS problem with path style. `GetAuthorizationToken`'s `proxyEndpoint` still names the virtual-host form (`000000000000.dkr.ecr.eu-west-2.localhost:<port>`) ([data-plane.log](23-01-evidence/data-plane.log)) | Registry from `ecr_repository_urls`; log in to the repository URL's host, not to `proxyEndpoint` |
| 5 | CloudFront refuses the ALB origin | **Confirmed**, and the cdn module's validation refuses Floci's ALB name too | Origin `localhost` plus the allowlist: `/api/health` through the distribution reached the ALB listener (`503 No targets available`, past the origin-header rule), while the listener without the header answers 403 ([cloudfront.log](23-01-evidence/cloudfront.log)) |
| 6 | Tasks can't reach RDS, ElastiCache, Floci | **Confirmed**, fix works at the address level: the cache endpoint is `floci-spike:6379`, the database `172.29.0.2:7001` (Floci's container IP); tasks join a per-VPC Docker network and Floci's network and resolve Floci's hostname ([data-plane.log](23-01-evidence/data-plane.log), [ecs.log](23-01-evidence/ecs.log)). The app's own connections were not exercised (no app image) | `FLOCI_HOSTNAME` and `FLOCI_SERVICES_DOCKER_NETWORK`; security groups left unenforced |
| 7 | ElastiCache TLS with verification | **Changed**: TLS is on and the certificate (issuer `Floci Local CA`) names `FLOCI_HOSTNAME`, but Floci 2.5.0 does **not** copy its CA into ECS task containers: no `/etc/floci-ca-bundle.pem`, no `SSL_CERT_FILE`. With TLS on, the queue URLs Floci returns are also `https://` | Not proven end to end. Proposed: the rehearsal adds Floci's root CA (in Floci's data volume, `tls/floci-root-ca.crt`) to the image it pushes and points `SSL_CERT_FILE` at it through the services' extra environment; fallback, `transit_encryption_mode` as a cache input |
| 8 | Postgres image without pgvector | **Confirmed**; fix works: `CREATE EXTENSION vector` gives 0.8.1 in the emulated RDS ([data-plane.log](23-01-evidence/data-plane.log)) | `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:0.8.1-pg16` |
| 9 | fck-nat AMI lookup | **Changed**: the lookup succeeds (Floci 2.5.0's catalogue has `fck-nat-al2023-20260101-arm64-ebs`, owner 568608671756), but the apply fails on the fck-nat interface's `source_dest_check` (`ModifyNetworkInterfaceAttribute is not supported`) | `managed_nat = true` |

Other research findings the spike settled:

- **15, drift**: half right. The RDS port drifts (Floci gives 7001 for the requested 5432), but `storage_type` reads back `gp3` and does not drift. Two drifts the research missed: the KMS keys' `rotation_period_in_days` reads back 0 (365 set), and the replication group's `maintenance_window` is not stored. A second plan shows 4 changes ([plan-after-apply.log](23-01-evidence/plan-after-apply.log)).
- **13, CPU scaling**: confirmed with the fix. `put-metric-data` of `AWS/ECS CPUUtilization` for the API service moved its target-tracking high alarm to ALARM after about 140 s and the API to 2 tasks ([autoscaling.log](23-01-evidence/autoscaling.log)).
- **11, CloudFront Functions**: confirmed. `/` is served through `default_root_object`; a deep link returns 404.
- **12, the URL**: confirmed. The `url` output is `https://<id>.cloudfront.localhost`, but Floci serves the distribution over HTTP on its own port.
- **16, memory**: Floci 2.5.0's image is a native build, not a JVM: 131 MB idle.

### Task protection, Fargate Spot, queue-depth scaling

- **ECS task protection**: the control-plane API works (`UpdateTaskProtection` and `GetTaskProtection` on a running task). There is no ECS agent endpoint: Floci sets no `ECS_AGENT_URI` in task containers and answers 404 on the agent's `task-protection/v1/state` path, so the app's `build_protection` picks `NoProtection` in a rehearsal, as in `make dev`. Not tested: whether Floci's service scale-in skips protected tasks.
- **Fargate Spot strategies**: supported as records. The cluster has both capacity providers, each service keeps its `capacityProviderStrategy` (worker-general `FARGATE_SPOT`), and a task started with `FARGATE_SPOT` runs with `capacityProviderName = FARGATE_SPOT`. No interruptions (per Floci's docs; not tested).
- **Scaling on SQS queue depth**: **partly**. Floci publishes the `AWS/SQS` metrics itself (`ApproximateNumberOfMessagesVisible`, `…NotVisible` and others), a plain alarm on one of them evaluates within a minute, and a step policy on such an alarm moved `worker-runs` from 0 to 2 tasks in 15 s. But the pools' alarms use metric math (`waiting + in_flight`) and Floci never evaluates them: they and an identical probe alarm stayed `INSUFFICIENT_DATA` for over 6 minutes, and `GetMetricData` with the same queries returned no result. So worker scaling does not work in Floci unaided ([autoscaling.log](23-01-evidence/autoscaling.log)).

### Memory, and a worker size for a 16 GB laptop

Measured ([memory.log](23-01-evidence/memory.log)):

| Part | Measured |
|---|---|
| Floci, its registry, pgvector and Valkey, idle | 131 + 16 + 40 + 4 MB, about 0.2 GB |
| One general-pool worker process ingesting the seed Documents (Docling, local Embedding Model, ingestion scan) | 0.34 GB imported, 1.49 GB after warm-up, 2.32 GB peak over three passes |
| The API process with its local models loaded and used (input Guardrail classifier and a query embedding) | 0.34 GB imported, 2.33 GB peak |
| One runs-pool worker process doing Run work (ticket 22-04) | 2.35 GB; a `--concurrency=2` tree about 4.7 GB |
| Beat (the worker app imported, no models) | about 0.34 GB |

At the AWS settings (`jobs_per_task = 2`) the stack needs about 0.2 + 2.3 (API) + 4.9 (general: parent + 2 processes) + 4.7 (runs) + 0.3 (Beat) ≈ 12.5 GB with the runs pool busy, before Docker, the OS and a browser: too much for 16 GB. With **`jobs_per_task = 1` for both pools and each worker task at 1 vCPU / 3 GB** (2.3 GB peak plus headroom; Floci applies task memory as a hard limit), the stack peaks at about 0.2 + 2.3 + 2.6 + 2.6 + 0.3 ≈ 8 GB, which fits. PDFs were not measured (Docling's layout models were not in the sandbox), so 3 GB is a floor for the general pool; the rehearsal should keep its seed to Markdown, DOCX and PPTX or measure a PDF first.

The API's AWS size is 512 CPU / 1024 MiB, below the 2.33 GB its local models take; Floci enforces task memory, so a rehearsal API at that size would be killed on its first Visitor message. `local` needs about 3 GB for the API. On AWS the same limit applies: recorded for ticket 22-09 to check, not changed here.

### Documents corrected

- [The research file](research/floci-findings.md) gains a "Spike results" section that marks each blocker and corrects the findings above.
- [Spec 23](../../specs/23-floci-rehearsal-spec.md): the module inputs (validations, KMS rotation and maintenance-window drift), the S3 Control host and state bucket, the CA, the port clash with `make dev`, images from Docker Hub, worker scaling needing a published metric, task protection, the memory numbers and the API size.
- Tickets [23-02](02-module-inputs-for-a-local-environment.md), [23-03](03-make-rehearse.md), [23-04](04-the-rehearsal-is-a-usable-studio.md) and [23-05](05-make-rehearse-scale.md) gain the criteria the spike showed they need; [23-06](06-on-demand-ci-job-and-guide.md) gains the Docker Hub note.

### No spike code merged; tests; glossary and ADRs

The commit holds only documents and these logs: no Terraform, script or app change, so no behaviour needs a test and coverage is unchanged. `make infra-check` and `make link-check` pass on the commit. No new domain term (the spec's words "rehearsal" and "emulator" are not glossary terms). No ADR changes: ADR-0021's queue-depth alarms are right for AWS; the metric-math gap is the emulator's, handled in `local` by spec 23.

## Gaps and best guesses

- The app never ran as a task (no image), so the app's connections to the cache (TLS), database, queues, bucket and KMS key through Floci, presigned URLs (research 10) and the trusted-proxy peer (14) are unproven; 23-03 and 23-04 prove them.
- The CA fix for blocker 7 is a proposal, untested.
- The port: two Floci containers can't both publish 4566. With `FLOCI_PORT` changed, the queue URLs Floci returns still say `:4566` and the image's health check (which probes 4566) reports unhealthy. Best guess: the rehearsal Compose file stops `make dev`'s Floci and runs on 4566, rather than using another port.
- How `000000000000.localhost` resolves for Terraform on a laptop was not tested; Floci's `localhost.floci.io` endpoint (public wildcard DNS to 127.0.0.1) is a likely alternative to a hosts entry.
- Scale-in skipping protected tasks, Spot interruptions and PDF memory were not tested.
- The spike's first destroy stopped on the cluster because a standalone task (the spike's own probe) was still running; an unfinished seed task would do the same.
