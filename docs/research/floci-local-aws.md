# Research: `terraform apply` against Floci, and what to simplify once there is a domain

Date: 2026-11-14. Scope: every resource and data source in `infra/modules/*` and `infra/envs/demo` (not `infra/bootstrap`).

**Sources and citation convention**

- **Floci** at commit `ad549728df3aa0a6cb644bc3bdaf21f4d12bb660` (2026-11-14, `pom.xml` version 2.4.0, CHANGELOG head 2.4.0 of 2026-10-31). `F:<path>:<line>` means `https://github.com/floci-io/floci/blob/ad549728df3aa0a6cb644bc3bdaf21f4d12bb660/<path>#L<line>`. Where the docs were silent or contradicted themselves, I read the Java handler source (cited the same way). I did not run Floci. Everything below comes from reading its docs and source.
- **Terraform AWS provider** (`main`, fetched 2026-11-14): `P:guide:<line>` = `website/docs/guides/custom-service-endpoints.html.markdown`; `P:cf:<line>` = `internal/service/cloudfront/distribution.go`, both in [hashicorp/terraform-provider-aws](https://github.com/hashicorp/terraform-provider-aws).
- **This repo**: plain `path:line`.
- **Inferred** marks anything I reasoned out but did not confirm in a source.

---

## Summary

**Verdict.** Floci's API coverage is broad enough that `terraform apply` of `envs/demo` can succeed once you make **about six small, mostly additive changes**: a provider endpoint block, `managed_nat = true`, a prefix-list catalog file for Floci, a looser `alb_dns_name` validation, a pgvector Postgres image, and a toggle for Redis TLS. RDS, ElastiCache, ECS and ECR are real Docker-backed services. ELBv2 and CloudFront forward real HTTP. Most other services are in-process emulation, and EC2 networking (NAT, VPC endpoints, routes) is metadata only.

Getting a **working Studio end to end** through the CloudFront URL is harder. Four things block it:

- Floci does not run CloudFront Functions, so the SPA fallback and the `/demo` routing break (F:docs/services/cloudfront.md:437).
- Floci refuses a custom origin that resolves to a private address unless that exact host is allowlisted (F:docs/services/cloudfront.md:303).
- `studio_url` and the CORS origin must be `https://` with no port (`infra/modules/ecs/variables.tf:278`, `infra/modules/storage/variables.tf:43`).
- Browser presigned uploads need a public S3 endpoint setting that the ecs module does not pass.

**Effort (estimate, inferred):**

- Apply succeeds: about 1–2 days (new `envs/local` root, roughly 6 module variables, Floci compose file).
- End-to-end runtime through the edge: another 2–4 days, with open risks (TLS trust, ARM64 emulation, SPA routing).
- The domain simplification below: about 2–3 days plus an ADR.

**Top recommendations**

1. **Add `infra/envs/local`** rather than bending `envs/demo`. It would have a local backend, a provider `endpoints {}` block pointing at `http://localhost:4566`, and `managed_nat = true`. It reuses the same modules. A few new module variables would carry the Floci-only differences: CPU architecture, Redis TLS, and the S3 public endpoint.
2. **Relax the AWS-hostname validations** (`alb_dns_name`, and possibly the static bucket domain), or set Floci's hostname so the generated names still match. Without one of these, `plan` fails at `infra/modules/cdn/variables.tf:46`.
3. **Once a domain exists, replace CloudFront with ALB path routing plus a tiny static "web" service.** ADR-0011 says CloudFront exists because "without a domain, ACM can't issue a certificate for the ALB" (`docs/adr/0011-single-cloudfront-origin.md:3`). ALB path routing keeps the same-origin property ADR-0011 cares about. It removes the cdn module, the static bucket's OAC policy, the secret origin header, the CloudFront prefix list and its trusted-proxy entries. It also gets rid of the Floci CloudFront gaps listed above. This is the highest-payoff simplification.
4. **Drop the four VPC interface endpoints.** They are not a domain workaround. They cost about 64 of the roughly 240 USD a month (`docs/deploy-demo.md:94,105`), and Floci only stores them as records.
5. **Stop pushing the unused `rag-agent-studio/studio` image to ECR (inferred to be unused).** It is a Vite dev-server image (`frontend/Dockerfile:1-2,39`), and no task definition references it (`infra/envs/demo/main.tf:92`).

---

## 1. Compatibility table

Depth key:

- **Docker**: real container backend.
- **In-proc**: emulated in process, with behaviour.
- **Data plane**: in-process, and also proxies real traffic.
- **Record**: management plane only (stored and described, no behaviour).
- **Gap**: will fail or misbehave.

Unless a row says otherwise, "Action" means what a local env needs.

### network (`infra/modules/network/main.tf`)

| Resource / data source | Line | Floci support, depth | Local action |
|---|---|---|---|
| `aws_vpc.this` | 10 | In-proc. CreateVpc and attributes (F:docs/services/ec2.md:356-366). With SG enforcement off, no Docker network isolation is applied (F:docs/services/ec2.md:202). | Keep. |
| `aws_default_security_group.this` | 20 | In-proc. A default SG exists per VPC (F:docs/services/ec2.md:362). Revoke matching is documented (F:docs/services/ec2.md:400). | Keep (inferred to work). |
| `aws_subnet.public` / `.private` | 26 / 38 | In-proc (F:docs/services/ec2.md:382-389). AZs are `region+suffix` (F:src/main/java/io/floci/aws/services/ec2/Ec2Service.java:1576). | Keep. |
| `aws_internet_gateway.this` | 50 | In-proc (F:docs/services/ec2.md:536-544). | Keep. |
| `aws_route_table.*`, `aws_route.*`, `aws_route_table_association.*` | 56-87, 206 | Record. CreateRoute accepts `NatGatewayId` and `NetworkInterfaceId` (F:docs/services/ec2.md:558). No VPC routing is emulated (F:docs/services/ec2.md:202). | Keep. |
| `aws_eip.nat` | 94 | In-proc. Allocate, Associate and Describe (F:src/main/java/io/floci/aws/services/ec2/Ec2QueryHandler.java:323-327). | Keep. |
| `aws_nat_gateway.this` (`managed_nat = true`) | 102 | Record only: "Creates a NAT gateway record" (F:docs/services/ec2.md:813). | **Use this path locally** (`managed_nat = true`, `infra/modules/network/variables.tf:291`). |
| `data.aws_ami.fck_nat` (default path) | 112 | **Gap.** DescribeImages only knows the catalog AMIs (F:docs/services/ec2.md:117-158). The catalog owners are Amazon, Canonical and others (F:src/main/resources/ec2/image-catalog.yaml:16,74), not fck-nat's `568608671756`. The data source finds nothing, so plan errors (inferred from the source). | Switch off with `managed_nat = true`. |
| `aws_security_group.fck_nat`, its rules, `aws_network_interface.fck_nat`, `aws_eip_association.fck_nat`, `aws_instance.fck_nat` | 129-204 | RunInstances would start a real container from the fallback image (F:docs/services/ec2.md:15,158). Pointless locally. | Switched off by `managed_nat = true`. |
| `data.aws_region.current` | 218 | Provider-side. | Keep. |
| `aws_vpc_endpoint.s3` (gateway) and `.interface` (4 services) | 220, 248 | Record. CreateVpcEndpoint, ModifyVpcEndpoint, DescribeVpcEndpointServices; `DnsOptions` ignored (F:docs/services/ec2.md:369-373). | Keep, or drop them (see S3 below). |
| `aws_security_group.endpoints` and its ingress rule | 229, 237 | In-proc. The rule response includes `securityGroupRuleSet`, which `aws_vpc_security_group_*_rule` needs (F:src/main/java/io/floci/aws/services/ec2/Ec2QueryHandler.java:3678). | Keep. |

### database (`infra/modules/database/main.tf`)

| Resource | Line | Floci support, depth | Local action |
|---|---|---|---|
| `aws_db_subnet_group.this` | 11 | In-proc. | Keep. |
| `aws_security_group.this` and `aws_vpc_security_group_ingress_rule.clients` | 20, 28 | In-proc. These are metadata unless SG enforcement is on, and enforcement applies to EC2 and ECS containers only (F:docs/services/ecs.md:896). | Keep. |
| `aws_db_parameter_group.this` (`rds.force_ssl`) | 42 | Stored, but **not applied**: "PostgreSQL and SQL Server databases do not take parameter group values yet" (F:docs/services/rds.md:622). | Keep. It does nothing, which is harmless. |
| `aws_secretsmanager_secret` and `_version` (`secret_string_wo`) | 64, 74 | In-proc (F:docs/services/secrets-manager.md:13,17). | Keep. |
| `aws_db_instance.this` | 85 | **Docker.** Floci runs a real Postgres behind a TLS-terminating auth proxy (F:docs/services/rds.md:37,1228-1230). `KmsKeyId` and `StorageEncrypted` are stored and checked against KMS (F:docs/services/rds.md:177-184). Engine version `16` is accepted as a major version (F:docs/services/rds.md:764). Gaps: (a) the default image is `postgres:16-alpine` (F:docs/services/rds.md:284), which has no pgvector, so the `CREATE EXTENSION vector` migration fails (inferred). (b) The requested port 5432 is outside the default proxy range 7001-7099, so Floci assigns another port (F:docs/services/rds.md:300-307). The module output passes the real port on (`infra/modules/database/outputs.tf:18`), but `port = 5432` (`infra/modules/database/main.tf:8,95`) shows as drift on the next plan (inferred). | Set `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:0.8.1-pg16`, the image `docker-compose.yml:76` already uses. Either set `FLOCI_SERVICES_RDS_PROXY_BASE_PORT=5432` (this clashes with the compose Postgres) or accept the drift. |

### cache (`infra/modules/cache/main.tf`)

| Resource | Line | Floci support, depth | Local action |
|---|---|---|---|
| `aws_elasticache_subnet_group.this` | 16 | In-proc (F:docs/services/elasticache.md:310). | Keep. |
| `aws_security_group.this` and its ingress rules | 25, 33 | In-proc. | Keep. |
| `aws_secretsmanager_secret` and `_version` | 46, 56 | In-proc. | Keep. |
| `aws_elasticache_replication_group.this` | 67 | **Docker** (Valkey 8 whatever `engine_version` says, F:docs/services/elasticache.md:356-366). AtRest and KMS are stored (F:docs/services/elasticache.md:79). With transit encryption on, the proxy terminates TLS with Floci's local CA (F:docs/services/elasticache.md:11-26). The docs also say `TransitEncryptionMode` is "control-plane metadata; it does not establish data-plane TLS" (F:docs/services/elasticache.md:455-460), so the docs contradict each other. `auth_token` rotation (`ROTATE`/`SET`) is not supported on modify (F:docs/services/elasticache.md:81), so bumping `auth_token_version` would fail (inferred). Port 6379 is the bottom of the proxy range, so it is honoured (F:compatibility-tests/compat-terraform/main.tf:290-297). | Keep. **Runtime:** the backend builds `rediss://…?ssl_cert_reqs=required` (`backend/app/core/settings.py:197-205`), so the task must trust Floci's CA. Fargate tasks cannot bind-mount it. Add a module toggle so the local env runs with `transit_encryption_enabled = false` and `REDIS_TLS=false`. |

### storage (`infra/modules/storage/main.tf`)

| Resource | Line | Floci support, depth | Local action |
|---|---|---|---|
| `data.aws_caller_identity.current` | 14 | STS returns account `000000000000` by default (F:docs/services/ec2.md:472-478). | Keep. Do **not** set `skip_requesting_account_id`. |
| `aws_s3_bucket.this`, public access block, ownership, SSE (KMS and AES256), lifecycle | 16-73, 138 | In-proc (F:README.md, "S3 In-process"). Block Public Access and bucket policy only take effect with `FLOCI_SERVICES_S3_ENFORCE_AUTH` (F:docs/services/s3.md:416,430). | Keep. Leave enforce-auth off, otherwise the `aws:SecureTransport` deny (`infra/modules/storage/main.tf:101-109`) blocks plain-HTTP presigned uploads (inferred). |
| `aws_s3_bucket_cors_configuration.documents` | 77 | In-proc. | The origin validation needs `https://` with no port (`infra/modules/storage/variables.tf:43`). See Terraform wiring. |
| `aws_cloudfront_origin_access_control.static` | 92 | In-proc. OAC signing and the SourceArn grant are honoured when S3 auth is enforced (F:docs/services/cloudfront.md:215-218, F:docs/services/cloudfront-private-origin.md). | Keep. |
| `aws_s3_bucket_policy.*` | 123, 130 | Stored. Evaluated only with enforce-auth. | Keep. |

### kms (`infra/modules/kms/main.tf`)

| Resource | Line | Floci support, depth | Local action |
|---|---|---|---|
| `data.aws_caller_identity`, `data.aws_partition` | 17, 19 | Provider and STS. | Keep. |
| `aws_kms_key.this` (rotation and rotation period) | 37 | In-proc: Encrypt, Decrypt, data keys, rotation (F:docs/services/kms.md:46-52). `RotationPeriodInDays` is parsed (F:src/main/java/io/floci/aws/services/kms/KmsJsonHandler.java). | Keep. |
| `aws_kms_alias.this` | 50 | In-proc (F:docs/services/kms.md:33). | Keep. |

### ecr (`infra/modules/ecr/main.tf`)

| Resource | Line | Floci support, depth | Local action |
|---|---|---|---|
| `aws_ecr_repository.this` (IMMUTABLE, scan on push, KMS) | 9 | In-proc control plane over a real `registry:2` (F:docs/services/ecr.md:4,74). Tag immutability is enforced and `scanOnPush` is stored (F:docs/services/ecr.md:36-38). The repository URI is `<acct>.dkr.ecr.<region>.localhost:4566/<repo>` (F:docs/services/ecr.md:5). | Keep. Consider dropping `rag-agent-studio/studio` (S7). |
| `aws_ecr_lifecycle_policy.this` | 29 | Stored, not enforced (F:docs/services/ecr.md:40). | Keep. |

### ecs (`infra/modules/ecs/main.tf`, `migrate.tf`, `seed.tf`)

| Resource / data source | Line | Floci support, depth | Local action |
|---|---|---|---|
| `data.aws_region.current` | main.tf:26 | Provider. | Keep. |
| `aws_iam_role.*`, `aws_iam_role_policy.*` (task, execution, migrate, seed) | main.tf:108,118,258,268; migrate.tf:60-76; seed.tf:72-94 | In-proc. Policies are not enforced unless `FLOCI_SERVICES_IAM_ENFORCEMENT_ENABLED` is set (F:docs/services/s3.md:389). Task-role credentials are vended only when that is switched on and the task is on a user-defined Docker network (F:docs/services/ecs.md:943-975). | Keep. |
| `aws_ecs_cluster.this` | main.tf:126 | **Docker.** | Keep. |
| `aws_cloudwatch_log_group.*` | main.tf:206; migrate.tf:50; seed.tf:63 | In-proc. `awslogs` containers stream to it (F:docs/services/ecs.md:174-178). | Keep. |
| `aws_ecs_task_definition.*` (FARGATE, awsvpc, ARM64, secrets, read-only root, ephemeral `/tmp`) | main.tf:276; migrate.tf:109; seed.tf:128 | **Docker.** Fargate rules are checked (F:docs/services/ecs.md:254-275). Secrets Manager `valueFrom` is resolved (F:src/main/java/io/floci/aws/services/ecs/container/SecretsManagerSelector.java). `AWS_ENDPOINT_URL` is injected so in-container SDKs reach Floci (F:src/main/java/io/floci/aws/services/ecs/container/EcsContainerManager.java:403-408). `ARM64` makes the task run `linux/arm64`, **under emulation on an x86 host** (F:docs/services/ecs.md:76-79). The worker runs Docling, so emulation will be very slow (inferred). | Add a `cpu_architecture` variable (currently hardcoded at `main.tf:288`, `migrate.tf:119`, `seed.tf:138`). |
| `data.aws_ec2_managed_prefix_list.cloudfront` | main.tf:322 | **Gap by default.** Only the S3 and DynamoDB lists are built in (F:docs/services/ec2.md:619-623, F:src/main/java/io/floci/aws/services/ec2/Ec2Service.java:1859-1881). `FLOCI_SERVICES_EC2_MANAGED_PREFIX_LIST_CATALOG_PATH` can add AWS-owned lists per region, with no reserved-name check on the catalog (F:docs/services/ec2.md:625-649, F:src/main/java/io/floci/aws/services/ec2/Ec2Service.java:1920-1967). | Mount a catalog with `{"eu-west-2":[{"prefixListId":"pl-3b927c52","prefixListName":"com.amazonaws.global.cloudfront.origin-facing","cidrs":["172.16.0.0/12"]}]}` (the CIDR is arbitrary), or make the rule optional. |
| `terraform_data.origin_secret` | main.tf:329 | Terraform core. | Keep. |
| `aws_security_group.alb`, `aws_vpc_security_group_ingress_rule.alb` (prefix-list source), `aws_vpc_security_group_egress_rule.alb_to_api` | main.tf:338,346,358 | In-proc. Prefix-list sources are parsed and validated in the source (F:src/main/java/io/floci/aws/services/ec2/Ec2QueryHandler.java:542-547; F:docs/services/ec2.md:665-670). The table row "prefix list sources are not stored" (F:docs/services/ec2.md:398) is stale. The ELBv2 proxy ignores SGs (F:docs/services/elb.md:225-231). | Keep, once the catalog exists. |
| `aws_lb.this` (internet-facing ALB, attributes) | main.tf:369 | **Data plane.** HTTP listeners forward to IP targets (F:docs/services/elb.md:5,198-200). `idle_timeout` and `drop_invalid_header_fields` attributes exist (F:src/main/java/io/floci/aws/services/elbv2/ElbV2DefaultAttributes.java:48,52). **Gap:** the DNS name is `{name}-{id}.elb.localhost.floci.io` (F:docs/services/elb.md:362; F:src/main/java/io/floci/aws/services/elbv2/ElbV2Service.java:305,375-380), which fails `infra/modules/cdn/variables.tf:46` (`\.elb\.amazonaws\.com$`). Listener port 80 binds on the Floci host and must be published (F:docs/services/elb.md:350). | Relax the validation, or set `FLOCI_HOSTNAME` so the suffix matches (the suffix is `config.hostname()`, ElbV2Service.java:379; side effects on other services are unverified). Publish port 80. |
| `aws_lb_target_group.api` (ip, health check) | main.tf:386 | Data plane. Health checks probe for real (F:docs/services/elb.md:213-216). The ECS service registers task IPs (F:docs/services/ecs.md:502-505). | Keep. |
| `aws_lb_listener.http` (fixed 403) | main.tf:406 | Data plane (`fixed-response`, F:src/main/java/io/floci/aws/services/elbv2/ElbV2DataPlane.java:1106). | Keep. |
| `aws_lb_listener_rule.origin_header` (`http-header` condition) | main.tf:426 | Data plane. The `http-header` condition is evaluated (F:src/main/java/io/floci/aws/services/elbv2/ElbV2DataPlane.java:1864). | Keep. |
| `aws_security_group.service`, egress and ingress rules; `aws_security_group.migrate`/`.seed` and egress | main.tf:448,469,483; migrate.tf:82,92; seed.tf:100,110 | In-proc. Enforced only with `FLOCI_NETWORK_SECURITY_GROUP_ENFORCEMENT_ENABLED` (F:docs/services/ecs.md:896). | Keep. Leave enforcement off: it also breaks task-role credentials (F:docs/services/ecs.md:993-995). |
| `aws_secretsmanager_secret.platform`, `_version.*` (incl. `secret_string_wo`) | main.tf:504-537 | In-proc. | Keep. |
| `aws_ecs_service.this` (Fargate, circuit breaker, ALB) | main.tf:539 | **Docker.** The service scheduler runs, the circuit breaker is modelled, and LB targets are registered (F:docs/services/ecs.md:487-505,545-549). | Keep. |

### cdn (`infra/modules/cdn/main.tf`)

| Resource / data source | Line | Floci support, depth | Local action |
|---|---|---|---|
| `aws_cloudfront_cache_policy.static`/`.dynamic`, `aws_cloudfront_origin_request_policy.dynamic`, `aws_cloudfront_response_headers_policy.static`/`.dynamic` | 17, 44, 71, 93, 123 | In-proc and applied at delivery: forwarding, including `allExcept` (F:docs/services/cloudfront.md:219-226), and response-header policies (F:docs/services/cloudfront.md:340-342). | Keep. |
| `aws_cloudfront_function.spa_fallback` | 142 | **Record only.** "Floci does not run CloudFront Functions" (F:docs/services/cloudfront.md:437,624,629). Deep links, `/demo` and `/demo/` break (`infra/modules/cdn/functions/spa-fallback.js:9-19`). | Keep for apply. For runtime there is no fix inside CloudFront. S1 removes the need. |
| `aws_cloudfront_distribution.this` | 152 | **Data plane.** Viewer requests are routed to S3 or custom origins for every method (F:docs/services/cloudfront.md:3-7,179-190). The S3 origin is recognised because the provider sends an empty `S3OriginConfig` when only OAC is set (P:cf:2328-2333; F:src/main/java/io/floci/aws/services/cloudfront/CloudFrontRequestRouter.java:312-314). Custom headers are added to origin requests (F:docs/services/cloudfront.md:197-201). The default certificate with `TLSv1` is accepted (F:docs/services/cloudfront.md:384-395). `ViewerProtocolPolicy` is stored, but I found no enforcement in the serving path (inferred, F:src/main/java/io/floci/aws/services/cloudfront/CloudFrontServingController.java:1157 only reads the origin policy). **Gap:** the ALB origin `*.elb.localhost.floci.io` resolves to loopback, and private origins are refused unless the exact host is in `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS` (F:docs/services/cloudfront.md:303,446). That host contains the ALB id, so it is only known after the first apply (inferred). The browser hostname is `{id}.cloudfront.localhost.floci.io`, and `FLOCI_SERVICES_CLOUDFRONT_DOMAIN_SUFFIX` makes the API return that name (F:docs/services/cloudfront.md:191-196,445,569-571). | Apply works. For runtime: set the domain suffix to `cloudfront.localhost.floci.io`, turn on TLS and publish 443 (F:docs/services/cloudfront.md:566-567), trust the Floci CA, and allowlist the ALB host after the first apply, then restart Floci. |
| `data.aws_route53_zone.this`, `aws_acm_certificate.this`, `aws_route53_record.validation`, `aws_acm_certificate_validation.this`, `aws_route53_record.alias` (only when `domain_name` is set) | 258, 265, 280, 291, 299 | Route 53 in-proc, changes `INSYNC` immediately (F:docs/services/route53.md:45). ACM auto-issues with validation `SUCCESS` (F:docs/services/acm.md:31). The zone must be pre-created for the data source. Public alias answers are not served over DNS (F:docs/services/route53.md:82). | Leave `domain_name = null` locally. This path applies if a zone is pre-created (inferred). |

### Out of scope, for completeness

- `infra/modules/ci-oidc` is used only by bootstrap (`infra/bootstrap/main.tf:189`).
- IAM `CreateOpenIDConnectProvider` is supported (F:docs/services/iam.md:637).

---

## 2. Terraform wiring for a local env

**Root module.** Create `infra/envs/local`, a copy of `envs/demo/main.tf` with these differences:

- **No S3 backend.** `envs/demo/backend.tf:6-10` hardcodes `backend "s3"` with `use_lockfile`. Use the default local backend. Floci documents S3 backend state with DynamoDB locking (F:docs/getting-started/terraform.md:111-131). It does not document the S3 native `use_lockfile` (conditional PUT), which is unverified. Note too that Floci's example uses the deprecated top-level `endpoint` argument. On Terraform ≥1.6 write `endpoints = { s3 = "…" }` and `use_path_style = true`.
- **Provider.** Point each service at Floci. The services used are `acm cloudfront ec2 ecr ecs elasticache elbv2 iam kms logs rds route53 s3 secretsmanager sts`; key names are from P:guide:184-349, `elbv2` at P:guide:195. Provider endpoints take precedence over env vars (P:guide:59-67).

  ```hcl
  locals { floci = "http://localhost:4566" }
  provider "aws" {
    region                      = var.aws_region   # any region works (F:README.md "Any published AWS region")
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    s3_use_path_style           = true
    # do NOT set skip_requesting_account_id: storage bucket names and the KMS key policy need the account id
    endpoints {
      acm = local.floci  cloudfront = local.floci  ec2 = local.floci  ecr = local.floci
      ecs = local.floci  elasticache = local.floci elbv2 = local.floci iam = local.floci
      kms = local.floci  logs = local.floci        rds = local.floci   route53 = local.floci
      s3  = local.floci  secretsmanager = local.floci sts = local.floci
    }
    default_tags { tags = merge(local.tags, { ManagedBy = "terraform" }) }
  }
  ```

  Alternatively, `AWS_ENDPOINT_URL=http://localhost:4566` alone covers every service (P:guide:48,64). That is lighter, but easier to point at the wrong account by mistake.

**Module inputs and toggles**

| Need | Exists today? | Proposed |
|---|---|---|
| Avoid fck-nat AMI lookup | Yes: `managed_nat` (`network/variables.tf:291`) | `managed_nat = true` |
| CloudFront prefix list | No | Floci catalog file (above), or `alb_ingress_prefix_list = optional` in ecs |
| `alb_dns_name` validation | No | Accept any hostname (`cdn/variables.tf:46`) |
| Task architecture | No (hardcoded `ARM64`) | `var.cpu_architecture` in ecs, default `ARM64` |
| Redis TLS | No (hardcoded `true`, `cache/main.tf:86-87`, `ecs/main.tf:156`) | `var.transit_encryption` in cache, passed to ecs |
| Browser S3 endpoint | No (`OBJECT_STORE_PUBLIC_ENDPOINT_URL`, `backend/app/core/settings.py:130`, is not set by `ecs/main.tf:160-167`) | `var.extra_environment` map in ecs |
| `studio_url` / CORS origin | Must be `https://host` with no port (`ecs/variables.tf:278`, `storage/variables.tf:43`) | Satisfied with Floci TLS on 443 plus the domain suffix. Otherwise relax the validations to allow a port. |
| RDS port drift | `port` is a local (`database/main.tf:8`) | `FLOCI_SERVICES_RDS_PROXY_BASE_PORT=5432`, or a variable |

**Floci container settings** (env vars cited above):

- Docker socket mounted.
- Published ports: `4566`, `443` (TLS), `80` (ALB listener), `6379-6399`, and `7001-7099` or `5432`.
- `FLOCI_TLS_ENABLED=true`
- `FLOCI_SERVICES_CLOUDFRONT_DOMAIN_SUFFIX=cloudfront.localhost.floci.io`
- `FLOCI_SERVICES_EC2_MANAGED_PREFIX_LIST_CATALOG_PATH=/etc/floci/prefix-lists.json`
- `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:0.8.1-pg16`
- `FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS=<alb dns name>`, after the first apply.

The ports 6379 and 5432 clash with the repo's own `docker-compose.yml:81,93`, so do not run both stacks at once.

**Deploy script.** `scripts/deploy/deploy.sh` will not work unchanged:

- It hardcodes `<acct>.dkr.ecr.$AWS_REGION.amazonaws.com` (`scripts/deploy/deploy.sh:49`). The push would go to real AWS. Floci rewrites that form only at ECS pull time (F:docs/services/ecr.md:100).
- It refuses non-arm64 images (`scripts/deploy/deploy.sh:58`).
- It runs `terraform init` with S3 backend config (`scripts/deploy/deploy.sh:44`).

Use `terraform output ecr_repository_urls` for the registry, and make the architecture check and backend configurable.

---

## 3. Simplification: what is a domain workaround, and what it becomes

Ranked by payoff, weighing infra removed, Floci friction removed, and risk.

### S1. CloudFront as the single TLS origin → ALB with ACM, path routing, and a small static "web" service (domain workaround: **yes**)

- **Why it exists:** "Without a domain, ACM can't issue a certificate for the ALB. So a single CloudFront distribution on its default `*.cloudfront.net` hostname terminates TLS" (`docs/adr/0011-single-cloudfront-origin.md:3`). Also `docs/specs/09-terraform-deploy-spec.md:5` ("no custom domain yet, yet … still need TLS") and the checkov skip text "there is no domain, so ACM cannot issue a certificate" (`infra/modules/ecs/main.tf:372`).
- **What is not a workaround:** the same-origin property. "Everything shares one origin, the Studio needs no CORS and no cross-site cookies" (ADR-0011:3). The backend relies on it: there is no CORS middleware in `backend/app`, and the widget docstring at `backend/app/embed/api.py:10` says so. Splitting into `app.` and `api.` subdomains would break that, so it is not proposed.
- **Simpler shape:** one hostname, `studio.example.com`, aliased in Route 53 to the ALB.
  - The ALB gets an HTTPS listener (ACM, DNS-validated in-region) and an HTTP→HTTPS redirect.
  - `/api/*` and `/widget/a/*` route to the api target group.
  - The default route goes to a `web` ECS service, an nginx or Caddy image holding the Studio, widget and `/demo` builds, with the SPA fallback as a `try_files` rule.
  - This removes the whole cdn module (7 resources plus 5 optional), the OAC and its bucket-policy grant, the static bucket (or keeps it only as an upload staging area), the CloudFront invalidation step, and the CloudFront Function and its Node test.
  - Optionally, the static files could be served from the API image instead. That couples frontend and backend images, so it is not preferred.
- **Effect on Floci:** large and positive. ELBv2 forwards HTTP and terminates HTTPS with ACM certificates that Floci auto-issues (F:docs/services/elb.md:136-137; F:docs/services/acm.md:31). It also removes every CloudFront gap: functions not run, the private-origin allowlist, and the edge hostname. Locally an HTTP-only listener toggle would do.
- **Risk and cost:**
  - You lose edge caching, HTTP/3 and the AWS edge for the widget. That is fine for a demo, but it rewrites spec 09 stories 17-19 and needs an ADR superseding ADR-0011.
  - SSE then runs straight from the ALB (`idle_timeout = 300`, `ecs/main.tf:381`), which is simpler than CloudFront's 60-second `origin_read_timeout` limit (`cdn/variables.tf:84-91`).
  - The web service adds about 8 USD a month at 0.25 vCPU (inferred from `docs/deploy-demo.md:93`), but that is offset by removing CloudFront.

### S2. Secret origin header, CloudFront prefix-list ingress, and prefix-list `TRUSTED_PROXIES` (domain workaround: **indirectly**)

- **Why they exist:** they are compensating controls for the plain-HTTP, internet-facing ALB origin: "the ALB accepts traffic only from CloudFront's managed prefix list carrying a secret origin header" (ADR-0011:3; spec 09 story 16, `docs/specs/09-terraform-deploy-spec.md:36`). `TRUSTED_PROXIES` includes CloudFront's ranges because those are "the only addresses the ALB admits" (`infra/modules/ecs/main.tf:168-172`; `backend/app/core/client_ip.py:8-14`).
- **Assessment:** a domain alone does **not** remove them. If CloudFront stays, AWS's usual pattern keeps the header and prefix list even with an HTTPS origin (general AWS guidance, not checked in a primary source here). They go away **only with S1**. Then the ALB is the public edge: ingress `0.0.0.0/0:443`, no header rule, and `TRUSTED_PROXIES = vpc_cidr`.
- **Effect on Floci:** removes the prefix-list catalog workaround and the `origin_header` secret. Locally, the ALB's peer address is the Floci container's Docker IP, not the VPC CIDR, so per-IP limits see one IP either way (inferred).
- **Risk:** low, if done together with S1.

### S3. Four VPC interface endpoints (domain workaround: **no**, accidental cost)

- **Why they exist:** "ECS image pulls, logs and secrets stay inside AWS instead of crossing the NAT" (`infra/modules/network/main.tf:213-216`; spec 09 module boundaries, `docs/specs/09-terraform-deploy-spec.md:58`).
- **Cost:** 8 ENIs at about 64 USD a month, about 27% of the 240 USD total (`docs/deploy-demo.md:94,105`). The repo already notes they could be dropped (`docs/deploy-demo.md:107`).
- **Simpler shape:** keep the free S3 gateway endpoint and drop the interface endpoints and their SG (3 resources across 4 instances).
- **Effect on Floci:** small. They are records only (F:docs/services/ec2.md:370).
- **Risk:** image pulls of the large worker image go through NAT (more slowly, and fck-nat bandwidth on `t4g.nano` is limited, inferred). Secrets and logs also cross NAT.

### S4. Optional custom-domain path in the cdn module (domain workaround: **yes, the reverse case**)

- **Why it exists:** spec 09 story 20 adds the domain "without restructuring" (`docs/specs/09-terraform-deploy-spec.md:40`; `infra/modules/cdn/main.tf:257-311`). The `TLSv1` floor and the HSTS-preload checkov skips exist only for the no-domain case (`infra/modules/cdn/main.tf:94,158,246-252`).
- **Once a domain exists:** make it required, delete the `custom_domain` conditionals, and pin `TLSv1.2_2021`. If S1 is done, the ACM and Route 53 resources move to the ALB instead.
- **Effect on Floci:** neutral. ACM and Route 53 both apply locally, with a pre-created zone.
- **Risk:** low.

### S5. `studio_url` and CORS origin taken from `module.cdn.url` (domain workaround: **yes**)

- **Why it exists:** the only stable public origin today is the generated `*.cloudfront.net` name (`infra/envs/demo/main.tf:63,98`; `infra/modules/cdn/outputs.tf:440-443`). That wires storage and ecs to cdn, and cdn back to storage and ecs (`infra/envs/demo/main.tf:57-65,84-131`).
- **Once a domain exists:** `local.public_url = "https://${var.domain_name}"`, known at plan time, with no cross-module edge.
- **Effect on Floci:** this is where the local env injects its own URL, so it removes the coupling between the port-free regex and the Floci hostname.
- **Risk:** none.

### S6. fck-nat instead of a managed NAT (domain workaround: **no**, a deliberate cost choice)

- **Why it exists:** "to keep an ephemeral demo environment cheap; a variable switches to a managed NAT" (`docs/adr/0010-aws-runtime-shape.md:3`; spec 09 Further Notes: "The HTTP origin hop and `fck-nat` are deliberate", `docs/specs/09-terraform-deploy-spec.md:100`).
- **Assessment:** keep it. It is about 4 USD against about 32 USD a month for a managed NAT, from general AWS pricing (not checked here). The local env must use `managed_nat = true` regardless.
- **Possible further simplification:** put tasks in public subnets with public IPs and drop NAT entirely. That is a security and posture trade, and not recommended.
- **Effect on Floci:** none beyond the toggle.

### S7. `rag-agent-studio/studio` ECR repository and push (domain workaround: **no**, inferred accidental)

- **Evidence:** the ecr module creates both repositories (`infra/envs/demo/main.tf:78`) and the deploy script pushes both (`scripts/deploy/deploy.sh:64`). Only the api repository feeds task definitions (`infra/envs/demo/main.tf:92-93`). The studio image is the local Vite dev server (`frontend/Dockerfile:1-2,39`), while the deployed Studio comes from `pnpm build` uploaded to S3 (`docs/deploy-demo.md:21`).
- **Simpler shape:** drop it, unless CI scans it from ECR (not checked).
- **Effect on Floci:** one fewer push.
- **Risk:** low.

### Not simplifications, but domain-dependent

- **SES email** stays off until a domain exists (`docs/specs/01-skeleton-auth-tenancy-spec.md:76,106`; `docs/specs/09-terraform-deploy-spec.md:95`). Adding a domain *adds* SES identity resources here.
- **The RDS parameter group** exists only for `rds.force_ssl` (`infra/modules/database/main.tf:41-53`). It is not a workaround, so keep it.

---

## 4. Runtime vs apply

| Piece | `apply` on Floci | Works at runtime? |
|---|---|---|
| VPC, subnets, routes, IGW, EIP, NAT, endpoints | Yes, with `managed_nat = true` | Metadata only. Containers share Docker networking, not VPC routing (F:docs/services/ec2.md:202). |
| KMS, Secrets Manager, Logs, IAM | Yes | Yes. Tasks reach them through the injected `AWS_ENDPOINT_URL`. boto3 1.43 (`backend/pyproject.toml`) honours it for the KMS client (`backend/app/crypto/adapters.py:16`, inferred). IAM is not enforced. |
| ECR | Yes | Push works through the Floci URI. ECS pulls from it (F:docs/services/ecr.md:100-101). |
| RDS Postgres | Yes (port drift) | Yes with the pgvector image. `ssl=require` works through the proxy's TLS (`backend/app/core/settings.py:194`; F:docs/services/rds.md:1230). Reaching the advertised endpoint host from task containers is inferred, not verified. |
| ElastiCache | Yes | Only with TLS off or the CA trusted. Token rotation is unsupported. |
| ECS services, migrate and seed tasks | Yes | Yes, but ARM64 is emulated on x86 hosts. The worker (2 vCPU / 8 GB with Docling) may be impractically slow (inferred). |
| ALB, target group, header rule | Yes, if the `alb_dns_name` validation is relaxed | Yes. HTTP forwarding and the header rule are evaluated. Port 80 must be published. |
| CloudFront distribution and policies | Yes | Partly. S3 and ALB origins proxy (the ALB only after the allowlist). Response headers apply. **The SPA fallback and `/demo` redirect never run**, so deep links 404 (inferred from F:docs/services/cloudfront.md:437). |
| CloudFront invalidations in `deploy.sh` | n/a | Yes, completed immediately (F:docs/services/cloudfront.md:165). |
| S3 presigned browser uploads | n/a | Only with `OBJECT_STORE_PUBLIC_ENDPOINT_URL` set to a browser-reachable Floci URL, plus CORS (inferred). |
| Session cookies (`secure=True`, `backend/app/auth/api.py:165`) | n/a | Need HTTPS in the browser, or a host the browser treats as a secure context. Plan on Floci TLS (open question below). |
| ACM and Route 53 (domain path) | Yes, with a pre-created zone | No public DNS for aliases (F:docs/services/route53.md:82). Cosmetic only. |
| Bedrock / model providers | n/a | Unaffected. Use `MODEL_GATEWAY=fake` locally as compose does (`backend/app/core/settings.py:95`). |

---

## 5. Open questions and things I could not verify

- **Unverified:** whether `terraform apply` actually succeeds. I did not run Floci or Terraform. Every "Yes" in the apply column comes from docs and source.
- **Unverified:** S3 backend `use_lockfile` (conditional PUT) against Floci S3.
- **Unverified:** whether `bucket_regional_domain_name` stays `*.s3.<region>.amazonaws.com` with a custom S3 endpoint. If not, `cdn/variables.tf:26` also needs relaxing.
- **Unverified:** whether setting `FLOCI_HOSTNAME=amazonaws.com` to make ALB names pass the regex has side effects on other services. I would not rely on it.
- **Contradiction in Floci docs:** ElastiCache transit TLS (F:docs/services/elasticache.md:11-26 vs 455-460). Test before relying on `rediss://` locally.
- **Unverified:** whether the CloudFront → ALB hop works once allowlisted. The ALB origin `*.elb.localhost.floci.io:80` resolves to 127.0.0.1 inside the Floci container, and the listener is in the same process (inferred).
- **Unverified:** `default_root_object = "index.html"` handling in Floci's CloudFront serving path. `/` might 403.
- **Unverified:** browser behaviour for `Secure` cookies on `http://{id}.cloudfront.localhost:4566`. The TLS-on-443 route avoids the question but needs the Floci CA trusted by the browser.
- **Unverified:** whether the RDS and ElastiCache advertised hosts are reachable from ECS task containers without `FLOCI_SERVICES_RDS_ENDPOINT_HOST` / `FLOCI_SERVICES_DOCKER_NETWORK` tuning (F:docs/services/rds.md:310-313; F:docs/services/elasticache.md:396-407).
- **Not checked:** whether CI scans the `studio` image from ECR (S7).
- **Not checked:** the AWS pricing figures in S3 and S6 beyond what `docs/deploy-demo.md` states.
