# Running rag-agent-studio's AWS Terraform on Floci: likely problems

Research for [spec 23](../../../specs/23-floci-rehearsal-spec.md), written before the infrastructure decisions in ADR-0021 were made: "Option A" below was the first proposal (public subnets), which was not adopted. Where spec 23 and this file differ, the spec is right.

Floci source read at version 2.5.0 (2026-11-15). Paths below: `repo:` = this repository, `floci:` = a clone of `floci-io/floci`.
No Docker daemon or Terraform in this sandbox (docker CLI only, no socket), so nothing was run. **verified** = seen in code/docs/issue; **inferred** = reasoning from those.
"Applies to": Current = today's modules; A = Option A (docs/infra-simplification.md); Both.

## Spike results (ticket 23-01, 2026-11-27)

[Ticket 23-01](../01-spike-terraform-apply-on-floci.md) applied the demo modules to Floci 2.5.0 with the Docker socket mounted; `terraform apply` reached the end. Where these results and the findings below differ, the results are right. Evidence: [23-01-evidence](../23-01-evidence/README.md).

| # | Finding | Result |
|---|---|---|
| 1 | No endpoint config | Confirmed; the fix works. Also needed: the state bucket created with `LocationConstraint=eu-west-2` before `init`, and the name `000000000000.<endpoint host>` resolving to Floci, because provider 6.x reads S3 bucket tags through S3 Control, which prefixes the account ID to the host (unresolvable, the apply hangs on the buckets) |
| 2 | ARM64 tasks | Confirmed (Floci asks for `linux/arm64` and refuses an amd64 image); `X86_64` fixes it |
| 3 | CloudFront prefix list | Confirmed; the catalogue fix works and accepts the reserved name |
| 4 | deploy.sh registry | Confirmed. Path-style ECR URIs (`localhost:<port>/000000000000/<region>/<repo>`) push over plain HTTP with no login; `GetAuthorizationToken`'s `proxyEndpoint` is still the virtual-host form. The ecs module's `image_repository_url` validation refuses the path-style URI |
| 5 | CloudFront origin | Confirmed; origin `localhost` plus the allowlist works (`/api/*` reaches the ALB listener with the origin header). The cdn module's `alb_dns_name` validation refuses Floci's ALB name `<name>-<16 hex>.elb.<FLOCI_HOSTNAME>` |
| 6 | Networking | Confirmed at the address level: cache `<FLOCI_HOSTNAME>:6379`, database `<Floci container IP>:7001`; tasks join a per-VPC network and Floci's. App connections not yet exercised |
| 7 | Cache TLS | **Changed**: the certificate names `FLOCI_HOSTNAME`, but 2.5.0 copies no CA into ECS task containers (no `/etc/floci-ca-bundle.pem`, no `SSL_CERT_FILE`). With TLS on, queue URLs are `https://` as well. The tasks need Floci's CA another way |
| 8 | pgvector | Confirmed; the image override works (`vector` 0.8.1) |
| 9 | fck-nat AMI | **Changed**: the lookup succeeds (Floci's catalogue has the fck-nat AMI), but the apply fails on `ModifyNetworkInterfaceAttribute` (the interface's `source_dest_check`). `managed_nat = true` still fixes it |
| 13 | Autoscaling | CPU: confirmed, `put-metric-data` scales the API. Queue depth: Floci publishes the `AWS/SQS` metrics and evaluates plain alarms, but **never evaluates metric-math alarms**, which is what the worker pools' alarms are; worker scaling needs help |
| 15 | RDS drift | Port confirmed; `storage_type` does not drift. Also drifting: KMS `rotation_period_in_days` (reads 0) and the replication group's `maintenance_window` (not stored) |
| 16 | Memory | Floci is a native image (131 MB idle), not a JVM. Measured: API with local models 2.33 GB, one general worker process ingesting 2.32 GB, one runs process 2.35 GB (22-04). A 16 GB laptop fits with `jobs_per_task = 1` and 1 vCPU / 3 GB per worker task (about 8 GB in all) |
| — | ECS task protection | The control-plane API works; there is no ECS agent endpoint (`ECS_AGENT_URI` unset), so the app uses `NoProtection` |
| — | Fargate Spot | Strategies are stored and honoured as records; a `FARGATE_SPOT` task runs |
| — | Docker Hub | Floci pulls pgvector, Valkey and `registry:2` by name; a rate limit (429) stops it. Pre-pulling from a mirror and tagging works |
| — | Port | Floci's health check probes 4566 and queue URLs keep `:4566` when `FLOCI_PORT` changes, so the rehearsal can't run beside `make dev`'s Floci on another port |

## Ranked findings

### Blockers

1. **Terraform/CLI have no Floci endpoint config** (Both, **verified**)
   - Evidence: repo:infra/envs/demo/main.tf:22-28 (provider has region + default_tags only); repo:infra/envs/demo/backend.tf (S3 backend, bucket/region from `-backend-config`); repo:scripts/deploy/*.sh call `aws` with no `--endpoint-url`. Floci's own Terraform example lists endpoints per service and its compat suite omits `cloudfront`/`elbv2` (floci:compatibility-tests/compat-terraform/provider.tf; floci:docs/getting-started/terraform.md).
   - Fix: export `AWS_ENDPOINT_URL=http://localhost:4566`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`, `AWS_REGION=eu-west-2` (the provider v6, the TF ≥1.6 S3 backend and AWS CLI v2 all read `AWS_ENDPOINT_URL`). In `infra/envs/local` provider set `s3_use_path_style = true`, `skip_credentials_validation = true`, `skip_metadata_api_check = true`. Keep keys out of the provider block (Checkov CKV_AWS_41). Backend: `-backend-config="use_path_style=true" -backend-config="skip_credentials_validation=true"`. `use_lockfile` works: S3 PutObject honours `If-None-Match` (floci:src/main/java/io/floci/aws/services/s3/S3Service.java:1194-1214).
   - Set `FLOCI_STORAGE_MODE=persistent` (or `hybrid`). The shipped image defaults to `memory` (floci:docs/configuration/storage.md:40-45), so a Floci restart loses the state bucket. ECS task state is memory-only in any mode (floci:docs/services/ecs.md "Restarts").

2. **ARM64 tasks on an x86 host** (Both, **verified**)
   - Evidence: `cpu_architecture = "ARM64"` at repo:infra/modules/ecs/main.tf:288, migrate.tf:119, seed.tf:138. deploy.sh:58-61 refuses any image that isn't arm64. Floci creates the container for `linux/arm64` (floci:docs/services/ecs.md:76-80), so an x86 host needs qemu binfmt. Docling/torch under emulation is impractically slow.
   - Fix: add an ecs module variable `cpu_architecture` (default `ARM64`; `X86_64` in local). Build the image with an empty `IMAGE_PLATFORM` (Makefile:88,113). Make deploy.sh's arch check compare against an `EXPECTED_ARCH` (default arm64). Apple Silicon hosts are fine as is.

3. **The CloudFront origin-facing managed prefix list does not exist** (Both, since Option A keeps the ALB rule; **verified**)
   - Evidence: `data "aws_ec2_managed_prefix_list" "cloudfront"` at repo:infra/modules/ecs/main.tf:322-324, used at :172 (TRUSTED_PROXIES) and :350 (ALB SG rule). Floci ships only the S3 and DynamoDB lists (floci:docs/services/ec2.md:656-660; floci:src/.../ec2/Ec2Service.java:2017). Open issue floci-io/floci#8634 (2026-11-16) says exactly that the data source fails.
   - Correction to the earlier finding: prefix-list SG sources *are* stored now. ec2.md:435 is stale; ec2.md:702-707 and Ec2Service.java:8404-8432 handle `PrefixListIds`.
   - Fix: mount a catalog and set `FLOCI_SERVICES_EC2_MANAGED_PREFIX_LIST_CATALOG_PATH` (ec2.md:662-684): `{"eu-west-2":[{"prefixListId":"pl-3b927c52","prefixListName":"com.amazonaws.global.cloudfront.origin-facing","cidrs":["127.0.0.0/8","<floci docker network CIDR>"]}]}`. Use the Docker network CIDR so TRUSTED_PROXIES (#14) covers the address the API really sees. **Inferred**: the catalog accepts the reserved `com.amazonaws.` name, because the reserved-name check is documented only for `CreateManagedPrefixList`.

4. **deploy.sh pushes to real AWS** (Both, **verified**)
   - Evidence: repo:scripts/deploy/deploy.sh:49 builds `<acct>.dkr.ecr.$AWS_REGION.amazonaws.com`, and :63-66 log in and push there. Floci's repository URI is `000000000000.dkr.ecr.<region>.localhost:4566/<repo>` (floci:docs/services/ecr.md:5,78).
   - Docker Engine 29's containerd image store treats `*.localhost` as an HTTPS registry (ecr.md:78), and this sandbox's docker client is 29.9.2.
   - Fix: read the registry from `terraform output -json ecr_repository_urls` (repo:infra/envs/demo/outputs.tf:21-24) instead of building it. Set `FLOCI_SERVICES_ECR_URI_STYLE=path`, which gives `localhost:4566/000000000000/eu-west-2/rag-agent-studio/api`. Publish Floci on host port 4566, because the daemon pulls task images through the host's `localhost:<port>` (ecr.md:100,151).

5. **CloudFront refuses the ALB origin** (Both, **verified** in code; **inferred** fix)
   - Evidence: the API origin is `var.alb_dns_name` (repo:infra/modules/cdn/main.tf:174-191). Floci's ALB DNS is `<name>-<random16hex>.elb.<FLOCI_HOSTNAME|localhost.floci.io>` (floci:src/.../elbv2/ElbV2Service.java:303-305,393-398). That resolves to loopback/private, and Floci rejects custom origins that resolve to loopback/private unless the exact host is allowlisted (floci:docs/services/cloudfront.md "Custom origins that resolve to loopback…"; config `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS`, cloudfront.md:447-452). The random id means the host can't be allowlisted before apply. The self-origin shortcut covers only Floci's own port, not 80 (CloudFrontServingController.java:987-1002).
   - Fix (inferred): in the local env pass `alb_dns_name = "localhost"` to the cdn module and set `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS=localhost`. CloudFront then dials localhost:80 inside the Floci container. ALB listeners bind there, and a single listener on a port answers any Host (elb.md:351-381). The `http-header` rule condition and the fixed-response default are implemented (ElbV2QueryHandler.java:1377, ElbV2DataPlane.java:1106).

6. **Tasks can't reach RDS, ElastiCache or Floci unless the networking is set up** (Both, **verified**)
   - Evidence: the ElastiCache endpoint is `FLOCI_HOSTNAME` or else `localhost` (floci:src/.../elasticache/ElastiCacheService.java:3330-3332; issue #6243). The RDS endpoint is Floci's container IP (RdsService.java:9266-9281, DockerHostResolver.java:42-69) on a proxy port from 7001-7099. Tasks get `AWS_ENDPOINT_URL` from Floci's base URL (EcsContainerManager.java:2045-2093).
   - Fix: run Floci in compose with `FLOCI_HOSTNAME=floci` and `FLOCI_SERVICES_DOCKER_NETWORK=<compose network>`, mounting `/var/run/docker.sock`. Publish 4566 (and optionally 7001-7099 and 6379-6399 for debugging from the host). Keep `FLOCI_NETWORK_SECURITY_GROUP_ENFORCEMENT_ENABLED=false`: our DB SG rules hard-code 5432 (repo:infra/modules/database/main.tf:8,35) while Floci serves 70xx.

7. **ElastiCache TLS with certificate verification** (Both, **verified** mechanism; **inferred** end to end)
   - Evidence: `transit_encryption_mode = "required"` (repo:infra/modules/cache/main.tf:212-213), `REDIS_TLS=true` (ecs/main.tf:156), and the app builds `rediss://…?ssl_cert_reqs=required` (repo:backend/app/core/settings.py:199-209). Floci terminates TLS with its own CA. The certificate SANs cover the configured Floci hostname (floci:docs/services/elasticache.md:9-35).
   - Floci copies `/etc/floci-ca-bundle.pem` into every launched container and sets `SSL_CERT_FILE`. That includes read-only root filesystem tasks since #6263 (floci:docs/configuration/tls.md "Containers Floci Launches").
   - Fix: `FLOCI_TLS_ENABLED=true` (the issue repro used it; tls.md does not say the bundle needs it) plus `FLOCI_HOSTNAME=floci`. Fallback if verification still fails: local-only `REDIS_TLS=false` with `transit_encryption_enabled=false`.

8. **Postgres image and pgvector** (Both, **verified**)
   - Evidence: the migration runs `CREATE EXTENSION IF NOT EXISTS vector` (repo:backend/migrations/versions/20261105_0001_enable_pgvector.py:19). Without an override, engine_version `"16"` maps to `postgres:16-alpine`, which has no pgvector (RdsService.java:9096-9108,9195-9225). `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE` *replaces* the image regardless of engine_version (`.orElseGet` only runs when it is unset).
   - The parameter group family `postgres16` passes Floci's prefix-only check (RdsService.java:9161-9168). `rds.force_ssl` is stored but not enforced (inferred; it isn't in the container args list, RdsContainerManager.java:1695-1710).
   - TLS still works: the Postgres proxy answers `S` to SSLRequest and terminates TLS (floci:src/.../rds/proxy/PostgresProtocolHandler.java:615-623), so asyncpg's `ssl=require` (settings.py:197, set because ecs/main.tf:151 passes `DATABASE_TLS=true`) connects. asyncpg doesn't verify the certificate in `require` mode.
   - Fix: `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:0.8.1-pg16`, the same image as repo:docker-compose.yml:76. No other extensions are used.

9. **fck-nat AMI lookup** (Current only, **verified**)
   - Evidence: repo:infra/modules/network/main.tf:112-127 looks up owner 568608671756. Floci's DescribeImages only knows its own catalog and the caller's AMIs (ec2.md:500-516), so the data source returns no result and plan fails.
   - Fix: `managed_nat = true` in the local env. The variable exists (network/variables.tf:32-36), and NatGateway and EIP are records (ec2.md:850-852). Option A removes the lookup.

### Likely (the deploy finishes but something doesn't work)

10. **Presigned S3 URLs point at `http://floci:4566`** (Both, **verified**)
    - Evidence: ECS sets no `OBJECT_STORE_ENDPOINT_URL` or `OBJECT_STORE_PUBLIC_ENDPOINT_URL` (repo:infra/modules/ecs/main.tf:160-167). boto3 1.43.124 (backend/uv.lock) then uses the injected `AWS_ENDPOINT_URL` for both the client and the presigner (repo:backend/app/storage/s3.py:20-53). The browser can't resolve `floci`, so Document uploads and downloads break.
    - Fix: add an `extra_environment` map to the ecs module. Local sets `OBJECT_STORE_PUBLIC_ENDPOINT_URL=http://localhost:4566`, and the CORS origin must match the Studio URL in #12.

11. **CloudFront Functions are not executed** (Both, **verified**)
    - Evidence: the SPA fallback at repo:infra/modules/cdn/main.tf:142-150,202-205. Floci stores functions but doesn't run them: cloudfront.md "Not Supported" and open issue #6695. `/` works through `default_root_object` (applied in CloudFrontServingController.java:510-516), so smoke.sh's `check_studio` passes, but Studio deep links return 404.
    - Fix: local-only `custom_error_response { error_code = 404 (and 403), response_code = 200, response_page_path = "/index.html" }`. Floci applies CustomErrorResponses (CloudFrontServingController.java:1227-1291). Alternatively, accept it and test deep links on AWS.

12. **The CloudFront URL resolves nowhere locally** (Both, **verified**)
    - Evidence: `url = "https://<id>.cloudfront.net"` (repo:infra/modules/cdn/outputs.tf:26-29) feeds STUDIO_URL (envs/demo/main.tf:98), the Documents CORS origin (:63) and smoke.sh. Floci also serves each distribution as `{id}.cloudfront.localhost[.floci.io]` on its own port (cloudfront.md "Every distribution is also served as…"). ViewerProtocolPolicy is not enforced on serving (it appears only in the serializer, CloudFrontController.java:2113-2146), so plain http works.
    - Fix: `FLOCI_SERVICES_CLOUDFRONT_DOMAIN_SUFFIX=cloudfront.localhost`. The local env builds `local.url = "http://${module.cdn.domain}:4566"` (add a domain output) and passes it to ecs `studio_url` and storage `documents_cors_allowed_origin`. curl and browsers resolve `*.localhost` themselves. `*.localhost.floci.io` needs public DNS.

13. **Autoscaling never scales on CPU** (A only, **verified**)
    - Evidence: Floci creates the target-tracking alarms and runs the control loop, but "Floci does not synthesize ECS CPU/memory metrics" and an alarm with no data stays `INSUFFICIENT_DATA` (floci:docs/services/applicationautoscaling.md "Control loop"). Container Insights publishes only task counts (ecs.md:605-627). The default cooldown is 300s.
    - Fix: push `AWS/ECS CPUUtilization {ClusterName,ServiceName}` with `aws cloudwatch put-metric-data` from a rehearsal script. Set `scale_in_cooldown`/`scale_out_cooldown` explicitly (small in local).
    - For the worker backlog metric, something must publish the Redis `LLEN` metric. A Beat task works and reaches Floci through `AWS_ENDPOINT_URL`. On AWS Beat's task role has no policy (ecs/main.tf:104), so it would need `cloudwatch:PutMetricData`.
    - Not Floci-specific but Option A will hit it: the services need `ignore_changes = [task_definition, desired_count]`, or every apply resets the count.

14. **TRUSTED_PROXIES doesn't contain the real peer** (Both, **inferred**)
    - Evidence: TRUSTED_PROXIES is the VPC CIDR plus the prefix list entries (repo:infra/modules/ecs/main.tf:172). The ALB and CloudFront data planes run inside the Floci JVM, so the API's peer is Floci's Docker-network IP (172.x), which is outside 10.0.0.0/16. client_ip (repo:backend/app/core/client_ip.py) then treats Floci as the Visitor, and every Visitor shares one rate-limit bucket.
    - Fix: put the Docker network CIDR and 127.0.0.0/8 in the catalog list (#3).

15. **RDS port and storage_type drift on every plan** (Both, **verified** issue; **inferred** effect)
    - Evidence: open floci-io/floci#4575 (updated 2026-11-11). Our `storage_type = "gp3"` and `port = 5432` (repo:infra/modules/database/main.tf:104,111) read back as gp2 and 70xx. Each deploy.sh apply then sends ModifyDBInstance. A port outside 7001-7099 gets the next free port (rds.md:323-330), so DATABASE_PORT can move between applies.
    - Fix: make `port` and `storage_type` module variables. Local passes `port = 7001` (inside the range) and `gp2`.

16. **The worker image under Floci on a laptop** (Both; Option A same sizes; **inferred**)
    - Evidence: the worker is 2 vCPU / 8 GB (repo:infra/modules/ecs/variables.tf:98-102). The image bundles torch CPU, Docling and OCR models (backend/pyproject.toml:13,31-47; Dockerfile:48-59), so it is several GB, and it is stored twice: the local image plus the registry:2 copy.
    - Also running: Floci's JVM, registry:2, pgvector, valkey, plus api, beat, migrate and seed. Plan for about 12-16 GB RAM and 20+ GB disk. Floci applies task memory as a hard limit and task CPU as a quota (ecs.md:131-134).
    - Fix: local `task_sizes.worker = {cpu=1024,memory=4096}` or the default, and run `docker system df` and `POST /_floci/ecr/gc` between runs.

### Minor

17. **Bedrock and STS calls go to Floci** (Both, **verified**). The injected `AWS_ENDPOINT_URL` sends every boto3 client to Floci, including Bedrock (repo:backend/app/credentials/bedrock_verifier.py:53-69). Floci's InvokeModel is a stub (floci:docs/services/bedrock-runtime.md:10,20), so the Bedrock provider and ExternalId AssumeRole paths are not exercised for real. Test them on AWS or with a non-Bedrock provider.
18. **IAM is not exercised** (Both, **verified**). IAM enforcement is off by default and task-role credentials are off by default (ecs.md:951,984-1023). Tasks run with Floci's baseline credentials, so the task, execution and KMS policies are not tested. Optionally set `FLOCI_SERVICES_ECS_TASK_ROLE_CREDENTIALS_ENABLED=true` (needs a user-defined network) and `FLOCI_SERVICES_IAM_ENFORCEMENT_ENABLED=true` as a second pass.
19. **S3 `aws:SecureTransport=false` deny** (Both, **verified**). The policy (repo:infra/modules/storage/main.tf:108) is inert by default because bucket policies are evaluated only with `FLOCI_SERVICES_S3_ENFORCE_AUTH` (s3.md:389-431). If you turn that on over http, every request is denied, so it would need TLS too.
20. **ElastiCache version and token rotation** (Both, **verified**). `engine_version 7.1` runs `valkey/valkey:8` (elasticache.md:373-397), which Celery should be fine with. For Redis-7 semantics set `FLOCI_SERVICES_ELASTICACHE_DEFAULT_IMAGE=valkey/valkey:7.2`. Bumping `auth_token_version` (ROTATE, cache/main.tf:214-216) fails: "Changing the AUTH token (ROTATE, SET) is not supported" (elasticache.md:81).
21. **ECS rollout semantics** (Both, **verified**). `services-stable` sees one synthetic PRIMARY deployment. `health_check_grace_period_seconds` is not enforced, so the ALB probes the API from t=0, and a slow-starting API under emulation can flap. The circuit breaker counts only tasks that fail to start (ecs.md:521-575). Spot capacity is honoured, but interruptions are not simulated (ecs.md:387-410, Option A). deploy.sh's run-task, wait, exitCode flow and seed.sh's log stream name `<prefix>/<container>/<task-id>` match Floci (ecs.md:174-178,326-331).
22. **New env vs CI gates** (**verified**). `infra/tests/backend.test.sh` requires every `envs/*/backend.tf` to have an s3 backend, `use_lockfile = true`, `key = "envs/<name>/terraform.tfstate"`, and no bucket. Makefile:85,102-110 run validate, `terraform test`, tflint (preset all) and checkov on `envs/*`. Hard-coded `access_key="test"` would fail CKV_AWS_41. `skip_*` provider flags are fine.

## What to build for `infra/envs/local`

- **`compose.floci.yml`** (Floci 2.5.0 pinned): mount the docker socket and publish 4566.
  - Env: `FLOCI_HOSTNAME=floci`, `FLOCI_SERVICES_DOCKER_NETWORK=<net>`, `FLOCI_STORAGE_MODE=persistent`, `FLOCI_TLS_ENABLED=true`, `FLOCI_SERVICES_ECR_URI_STYLE=path`, `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:0.8.1-pg16`, `FLOCI_SERVICES_ELASTICACHE_DEFAULT_IMAGE=valkey/valkey:7.2`, `FLOCI_SERVICES_EC2_MANAGED_PREFIX_LIST_CATALOG_PATH=/etc/floci/prefix-lists.json`, `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS=localhost`, `FLOCI_SERVICES_CLOUDFRONT_DOMAIN_SUFFIX=cloudfront.localhost`, `FLOCI_DEFAULT_REGION=eu-west-2`.
  - Plus the mounted catalog JSON (#3).
- **`infra/envs/local/`**: the same module composition as demo.
  - Provider: path style and `skip_*` flags, credentials from env.
  - `backend.tf`: s3, `use_lockfile`, `key = envs/local/terraform.tfstate`.
  - Inputs: `managed_nat = true` (or Option A's `private_networking = false`), `cdn.alb_dns_name = "localhost"`, a 404→`/index.html` custom error response.
  - Its own http Studio URL wired into `studio_url` and the CORS origin.
- **Module variables to add**:
  - ecs: `cpu_architecture`, `extra_environment` (for `OBJECT_STORE_PUBLIC_ENDPOINT_URL`).
  - database: `port`, `storage_type`.
  - cdn: a `domain` output, and an optional `custom_error_responses` input.
- **Script changes**:
  - deploy.sh takes the registry from the `ecr_repository_urls` output and the architecture from `EXPECTED_ARCH`.
  - A `scripts/deploy/local.sh` wrapper exports `AWS_ENDPOINT_URL` / test credentials, creates the state bucket with `aws s3 mb`, and sets `DEPLOY_ROOT=infra/envs/local`.
- **Option A rehearsal helper**: a script that `put-metric-data`s CPUUtilization and the backlog metric, with short cooldowns in local.
- **Not covered by Floci (test on AWS)**: the CloudFront Function, IAM, Bedrock, and security groups.
