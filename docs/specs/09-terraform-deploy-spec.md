# Spec 09: Terraform and deploy

## Problem Statement

The product runs well locally, but an interview capstone also needs to show it can run in the cloud, defined as code, deployed by a pipeline, and torn down again. Leaving it running costs money, so the environment has to be cheap to keep and easy to destroy. There's no custom domain yet, yet the Studio, widget and API still need TLS. Credentials and data in the cloud must be protected properly: private networking, encryption, least-privilege roles, and no long-lived CI secrets.

## Solution

Terraform modules for every piece of the AWS runtime, composed in an `envs/demo` root module:
- **Networking:** VPC and subnets, with `fck-nat` egress (a managed NAT is a toggle).
- **Data and storage:** RDS Postgres with pgvector, ElastiCache Redis, S3 buckets.
- **Compute:** ECS Fargate services for the API, worker and Beat.
- **Edge:** an ALB reachable only from CloudFront, and one CloudFront distribution routing by path on its default domain.
- **Keys and images:** KMS, Secrets Manager, ECR.
- **CI access:** a GitHub OIDC role.

Remote state lives in S3 with native locking. GitHub Actions builds and pushes images on `main` and offers manual apply and destroy runs. Migrations run as a one-off ECS task before services roll. A `domain_name` variable adds Route 53 and ACM when a domain exists. Every module has `terraform test` coverage and passes `fmt`, `validate`, `tflint` and `checkov` in CI.

## User Stories

1. As a developer, I want the whole AWS environment defined in Terraform, so that it's reproducible and reviewable.
2. As a developer, I want reusable modules (network, database, cache, storage, ECS, CDN, KMS, CI OIDC) composed by an environment root module, so that adding an environment later is mostly configuration.
3. As a developer, I want remote state in S3 with native S3 state locking, so that state is safe and shared without a DynamoDB table.
4. As a developer, I want a documented bootstrap step that creates the state bucket and the GitHub OIDC role once, so that the first apply is possible from CI.
5. As a developer, I want application services in private subnets with egress through a single `fck-nat` instance, so that the demo is cheap and still private.
6. As a developer, I want a variable that switches to a managed NAT gateway, so that a production-like setup is one change away.
7. As a developer, I want Postgres 16 on RDS with pgvector enabled, encrypted, in private subnets, with automated backups, so that data is protected.
8. As a developer, I want Redis on ElastiCache with encryption in transit and at rest and auth enabled, so that the broker and rate-limit store are protected.
9. As a developer, I want private, encrypted S3 buckets for Documents and for static assets, with public access blocked and CloudFront origin access control for static assets, so that nothing is accidentally public.
10. As a developer, I want a CORS rule on the Documents bucket that allows presigned uploads only from the CloudFront origin, so that browser uploads work and nothing else.
11. As a developer, I want the API, worker and Beat as separate ECS Fargate services with right-sized CPU and memory (worker sized for Docling), so that each scales and fails independently.
12. As a developer, I want separate least-privilege IAM task roles for each service, so that, for example, only the worker and API can read Document objects and only the API can use the KMS key for credentials.
13. As a developer, I want the API task role allowed to assume customer Bedrock roles only with an external ID, so that cross-account access follows AWS guidance.
14. As a developer, I want a KMS key for Provider Credential envelope encryption with rotation enabled, so that ADR-0006 holds in the cloud.
15. As a developer, I want platform secrets (database password, Redis auth, session secret, origin header secret) in Secrets Manager and injected into tasks, so that no secret lives in Terraform variables or images.
16. As a developer, I want the ALB to accept traffic only from CloudFront's managed prefix list carrying the secret origin header, so that the plain-HTTP origin hop can't be bypassed.
17. As a developer, I want one CloudFront distribution routing `/`, `/embed.js`, `/widget/assets/*`, `/widget/a/*` and `/api/*`, with caching only for static paths, so that everything is served over TLS from one origin.
18. As a developer, I want CloudFront to forward the headers, cookies and query strings the API needs and disable buffering for SSE, so that streaming chat works through the CDN.
19. As a developer, I want SPA fallback routing for the Studio, so that deep links work.
20. As a developer, I want an optional `domain_name` that adds Route 53 records and an ACM certificate, so that a real domain can be added without restructuring.
21. As a developer, I want ECR repositories with scan on push and lifecycle rules, so that images are scanned and old ones cleaned up.
22. As a developer, I want CloudWatch log groups with retention for every service, and container logs in structured JSON, so that the demo is debuggable and cheap.
23. As a developer, I want Logfire's token supplied through Secrets Manager when present, so that tracing works in the cloud when enabled.
24. As a developer, I want images built and pushed to ECR on every merge to `main` when AWS is configured, so that a deployable artifact always exists.
25. As a developer, I want a manual workflow to apply the demo environment at a chosen image tag, so that I can bring the demo up before an interview.
26. As a developer, I want migrations run as a one-off ECS task, gated on success, before services are updated, so that the schema is always ready for the new code.
27. As a developer, I want a manual workflow to destroy the demo environment, so that I stop paying once the interview is over.
28. As a developer, I want `terraform plan` posted on PRs that touch infrastructure when the OIDC role is configured, and skipped cleanly otherwise, so that CI is green without an AWS account.
29. As a developer, I want CI to authenticate to AWS through GitHub OIDC with a role limited to this repository's branches, so that there are no long-lived AWS keys in GitHub.
30. As a developer, I want `fmt`, `validate`, `tflint` and `checkov` on every PR, with any checkov skips justified inline, so that infrastructure quality is enforced.
31. As a developer, I want `terraform test` for each module asserting its contract (outputs, encryption flags, access rules, routing), so that module changes are verified without deploying.
32. As a developer, I want the apply workflow to print the CloudFront URL and run a smoke check (health endpoint, Studio loads, widget shell responds with CSP), so that I know the deploy works.
33. As a developer, I want sensible tags on every resource (project, environment, managed-by), so that costs are traceable and cleanup is easy.
34. As a developer, I want a documented rough monthly cost for the demo environment, so that I know what leaving it up costs.

## Implementation Decisions

- **Module boundaries:** `network` (VPC, subnets across two AZs, `fck-nat` or managed NAT toggle, VPC endpoints for S3, ECR, Logs and Secrets Manager to reduce NAT traffic), `database`, `cache`, `storage` (Documents bucket, static bucket, origin access control), `kms`, `ecs` (cluster, task definitions, services, task roles, log groups, ALB with prefix-list ingress and origin-header listener rule), `cdn` (distribution, behaviours, cache and origin-request policies, SPA fallback function, optional ACM and Route 53), `ecr`, `ci-oidc` (GitHub OIDC provider and deploy role). Each module exposes a small set of inputs and outputs. The environment root module wires them together.
- **State:** an S3 backend with `use_lockfile` (native locking), and the bucket created by a bootstrap root module applied once by hand (documented in the README).
- **Cost defaults for the demo:** `db.t4g.micro` RDS single-AZ, a `cache.t4g.micro` single node, Fargate with ARM64 images, worker at 2 vCPU / 8 GB, API at 0.5 vCPU / 1 GB, and a `fck-nat` `t4g.nano`. Every value is a variable.
- **pgvector:** enabled by a migration (`CREATE EXTENSION vector`), which RDS Postgres 16 supports. No custom parameter group is needed beyond sensible defaults.
- **CloudFront behaviours:**
  - Static paths: cached, compressed, served from S3 through origin access control.
  - `/api/*` and `/widget/a/*`: caching disabled, all viewer headers except Host forwarded, cookies and query strings forwarded, the origin-header secret added, an origin read timeout long enough for SSE.
  - Price class 100.
- **ALB:** an HTTP listener whose security group allows only the CloudFront managed prefix list. A listener rule requires the secret header and returns 403 otherwise (ADR-0011).
- **Images:** one backend image for API, worker and Beat with different commands (the worker variant bakes in the Docling, embedding and classifier models), plus static frontend builds uploaded to S3 by the deploy workflow, with CloudFront invalidated for HTML and `embed.js`.
- **Deploy workflow.** Apply with the given image tag → run the migration task and wait → update services and wait until stable → upload static assets → invalidate → smoke check. Destroy is a separate dispatch with a typed confirmation input.
- **Security scanning:** checkov runs with a committed baseline that's empty at the start. Every skip carries an inline justification (for example, the HTTP-only ALB, justified by ADR-0011).
- **Outputs:** the CloudFront URL, the ECR repository URLs, the Bedrock external-ID trust-policy principal (the API task role ARN, which the Studio shows in spec 02's helper).

## Testing Decisions

- **Good tests** assert each module's contract: given inputs, which resources are configured with what security-relevant attributes, and which outputs are produced. They don't snapshot whole plans.
- **Module seam (`terraform test`, plan mode with mocked providers):**
  - network: NAT toggle produces `fck-nat` or a managed NAT; private subnets have no public IPs.
  - database: encryption on, not publicly accessible, backups enabled.
  - cache: transit and rest encryption, auth on.
  - storage: public access blocked, encryption on, the Documents bucket CORS rule limited to the CloudFront origin.
  - kms: rotation on.
  - ecs: ALB ingress limited to the prefix list, the header rule, task roles least-privilege (assert on policy documents), and the assume-role condition requiring an external ID.
  - cdn: each path behaviour, caching disabled for the dynamic paths, the optional domain adds ACM and Route 53 only when set.
  - ci-oidc: trust limited to this repository.
- **Static analysis:** `fmt -check`, `validate`, `tflint` with the AWS ruleset, `checkov` in CI on every PR.
- **Plan on PR:** runs only when the OIDC secret is configured. The job is skipped, not failed, otherwise.
- **Deploy smoke check:** the apply workflow's final step hits the health endpoint, loads the Studio HTML, and fetches a widget shell to assert the CSP header. It runs only in the deploy workflow.
- **Prior art:** CI wiring from spec 01 (the infra workflow exists with stubs). This spec fills in the modules.

## Out of Scope

- Multiple regions or environments beyond `demo` (the structure supports adding them).
- Autoscaling policies beyond a fixed desired count.
- WAF (noted as a future addition in front of CloudFront).
- Blue/green or canary deployment strategies.
- SES set-up (it needs a domain; the mailer stays on console logging in AWS until then).

## Further Notes

- Write the expected monthly cost in the README, both "always on" and "apply for a day".
- ADR-0010 and ADR-0011 govern this spec. The HTTP origin hop and `fck-nat` are deliberate.
