# Spec 23: Rehearsing the AWS deployment on Floci

**Status:** ready-for-agent · **Builds on:** [Spec 09](./09-terraform-deploy-spec.md), [Spec 22](./22-lean-scalable-infrastructure-spec.md) (must land first) · **Decisions:** [ADR-0021](../adr/0021-sqs-two-worker-pools-autoscaling.md), [ADR-0011](../adr/0011-single-cloudfront-origin.md) · **Research:** [likely problems running the Terraform on Floci](../tickets/23-floci-rehearsal/research/floci-findings.md)

## Problem Statement

The only way to find out whether the Terraform and the deploy scripts work is to apply them to a real AWS account. That costs money, takes most of an hour for a round trip, and needs credentials, so mistakes in a module or in `deploy.sh` are found late, in the deploy workflow. The Terraform tests check each module's plan against a mocked provider; nothing runs the whole flow (apply, push images, migrate, roll the services, upload the Studio, smoke check) before AWS does. And the scaling behaviour from spec 22 can only be watched on a paid demo.

## Solution

One command rehearses the AWS deployment on a laptop against Floci, an open-source AWS emulator, with no AWS account.

`make rehearse` starts Floci, applies the same Terraform modules through a `local` environment, pushes the images to Floci's registry, runs the migration task, rolls the services as containers, uploads the Studio and widget, and runs the existing smoke check against the emulated CloudFront address. The Studio can then be opened in a browser and used. A second command puts jobs on the queues and shows the worker pools scale out and in. `make rehearse-down` removes everything.

The rehearsal proves the wiring, the deploy order and the scripts. It does not prove what Floci doesn't enforce or run: IAM policies, security groups, the CloudFront Function, Spot interruptions and Bedrock still need the real-AWS run in spec 22.

## User Stories

### Running a rehearsal

1. As a developer, I want `make rehearse` to bring up the whole AWS shape on Floci and finish with the smoke check, so that I know the deploy flow works before I pay for it.
2. As a developer, I want the rehearsal to use the same modules as the demo environment, through a `local` environment that differs only in inputs, so that what I rehearse is what I deploy.
3. As a developer, I want the rehearsal to need no AWS account or credentials, so that anyone who clones the repository can run it.
4. As a developer, I want the rehearsal to run the unchanged deploy script with a wrapper that points it at Floci, so that the script itself is what gets tested.
5. As a developer, I want Terraform state for the rehearsal kept in a bucket inside Floci, with locking, so that the backend configuration is exercised too.
6. As a developer, I want `make rehearse-down` to destroy the environment and remove Floci's containers and data, so that nothing is left running.
7. As a developer, I want a second `make rehearse` to succeed after a first, so that it is repeatable.
8. As a developer, I want the rehearsal to work on Intel and Apple-silicon laptops, so that the ARM64 choice for AWS doesn't exclude anyone.
9. As a developer, I want a clear message when my machine has too little memory or no Docker socket access, so that I'm not left reading a failed apply.

### What must work inside it

10. As a developer, I want the API and worker containers to reach the emulated database, cache, queues, bucket and key service by the addresses Terraform gives them, so that the same settings path is used as on AWS.
11. As a developer, I want the emulated database to have pgvector, so that the migrations run.
12. As a developer, I want the cache connection to use TLS and its auth token as on AWS, so that the secure settings path is rehearsed.
13. As a developer, I want the images pushed to and pulled from Floci's registry by the deploy script, so that the registry address comes from Terraform's outputs and is never assumed.
14. As a developer, I want the emulated CloudFront address to serve the Studio and forward `/api/*` to the load balancer with the secret origin header, so that ADR-0011's layout is rehearsed.
15. As a developer, I want to open the Studio at the rehearsal's address, sign in after seeding, upload a Document and see it become Ready, so that the rehearsal is a usable product and not only a passing script.
16. As a developer, I want browser uploads to work, so that presigned links point somewhere my browser can reach.
17. As a developer, I want Studio deep links to load after a refresh, so that the missing CloudFront Function doesn't make the Studio look broken.
18. As a developer, I want per-Visitor rate limits to see the real client address, so that the trusted-proxy setting is rehearsed correctly.
19. As a developer, I want the seed to run as a one-off task as it does on AWS, so that the seed script is rehearsed.
20. As a developer, I want a second `terraform plan` after an apply to show no changes, so that drift caused by the emulator doesn't hide real drift.

### Scaling

21. As a developer, I want a command that queues a batch of jobs and shows the general pool scale out and back, so that queue-depth scaling can be watched locally.
22. As a developer, I want the runs pool shown starting from zero for an Evaluation Run and returning to zero, so that scale-to-zero is rehearsed.
23. As a developer, I want the same command to feed a CPU figure for the API service and show it scale, so that the API's policy is rehearsed even though Floci produces no CPU metrics.
24. As a developer, I want short cooldowns in the local environment, so that a rehearsal takes minutes.
25. As a developer, I want the worker sized down in the local environment, so that the rehearsal fits a 16 GB laptop.

### Keeping it honest

26. As a developer, I want the rehearsal available as an on-demand CI job that is not required on every push, so that it can be run on a pull request that touches the infrastructure without slowing everything else.
27. As a developer, I want the `local` environment to pass the same format, validation, lint and security checks as the demo environment, so that it can't rot.
28. As a developer, I want the guide to list what the rehearsal does not prove, so that nobody skips the real-AWS run because the rehearsal passed.
29. As a developer, I want Floci pinned to a version and the emulator settings kept in one file with a comment on each, so that an upgrade is deliberate and each workaround is explained.
30. As a developer, I want each workaround for an emulator gap to be an input of the `local` environment and never a branch inside a module on "is this local", so that modules stay honest about AWS.

## Implementation Decisions

- **`local` environment.** A new environment root beside `demo` that composes the same modules. It differs only in inputs and provider settings (path-style S3, skipped credential checks, endpoint from the environment). Its state is in an S3 backend with a lock file, in a bucket the wrapper creates in Floci.
- **Rehearsal Compose file.** A separate Compose file, not part of `make dev`, that runs Floci with the Docker socket mounted so it can start the emulated database, cache, registry and tasks as containers on one network. The emulator's settings live in this file. It is the same pinned Floci version that `make dev` uses for SQS. Both publish port 4566 (Floci's health check and its queue URLs assume 4566, so another port doesn't work), so the rehearsal stops `make dev`'s Floci first. Floci pulls the pgvector, Valkey and registry images by name from Docker Hub; the rehearsal pre-pulls them so a Docker Hub rate limit gives a clear message rather than a failed apply.
- **Module inputs added so `local` can differ without branching.**
  - Compute: the CPU architecture of tasks; extra environment variables for the services; an image repository address that may be the emulator's path-style registry (`localhost:<port>/<account>/<region>/<repo>`), which the module's validation refuses today.
  - Database: the port, which the emulator reads back differently (the spike found the storage type reads back unchanged, so no input is needed for it). The emulator's database serves no TLS, so the compute module's database connection takes a TLS switch, on by default (ticket 23-03).
  - Drift the spike found elsewhere: the KMS keys' rotation period reads back as 0 and the cache's maintenance window is not stored, so both become inputs `local` can leave unset.
  - CDN: optional custom error responses; the distribution's domain as an output; the origin's address as an input the environment can override (`localhost` in `local`), with the module's `.elb.amazonaws.com` validation moved onto that input.
  - Network: `local` sets the existing managed-NAT toggle, because the emulator cannot set the `fck-nat` network interface's source/destination check (the image lookup itself works).
- **CloudFront's origin-facing addresses.** The managed prefix list the load balancer admits is supplied to the emulator as a catalogue file containing loopback and the Docker network range. The same ranges are added to the trusted proxies in `local`.
- **Addresses.** The emulated distribution is served on a `cloudfront.localhost` name over HTTP. That URL is the Studio URL and the uploads CORS origin in `local`. Presigned links use a public endpoint override that the browser can reach.
- **Deep links.** `local` adds a 404-to-index custom error response, because the emulator stores CloudFront Functions without running them.
- **Database and cache images.** The emulator is told to use the same pgvector image as `make dev`, and a Valkey release compatible with Redis 7. The emulator does not give its tasks its certificate authority (the spike found no CA bundle in task containers), so the rehearsal adds the emulator's CA to the image it pushes and points `SSL_CERT_FILE` at it through the services' extra environment; the cache's TLS setting then stays on. With TLS on, the queue URLs are HTTPS too, and need the same CA.
- **Deploy script.** Takes the registry address from Terraform's outputs and the expected image architecture from an argument, defaulting to today's behaviour. It logs in to the registry host in the repository address (the emulator's login endpoint names a different host). A wrapper script exports the emulator endpoint and test credentials, makes `<account>.<endpoint host>` resolve to the emulator (the AWS provider reads bucket tags through S3 Control, which prefixes the account ID to the host), creates the state bucket in the region, selects the `local` environment and calls the unchanged deploy, seed and destroy scripts.
- **Scaling helper.** A script that queues jobs through the API, publishes a CPU figure for the API service to the emulator's CloudWatch, and prints the same timeline as spec 22's scaling script. Worker scaling needs help too: the emulator publishes queue depth itself, but it never evaluates metric-math alarms, and the pools' alarms add two queue metrics. The helper therefore drives the pools' alarms from the queues' depth (`set-alarm-state`), which the emulator follows with the step policies; if it does not, a module input that switches the pools' alarms to a single metric is the fallback.
- **Security groups and IAM.** Left unenforced in the emulator, which is its default. The guide says so.
- **Make targets.** `rehearse`, `rehearse-scale`, `rehearse-down`, and the `local` environment added to `infra-check`.
- **CI.** One workflow, run by hand, that runs `make rehearse` and `make rehearse-down` and uploads the logs.
- **Guide.** A section in the deploy guide: prerequisites (Docker with socket access, Terraform, about 16 GB of memory), the commands, what the rehearsal proves, and what only AWS proves.

## Testing Decisions

- **Good tests** assert what a module produces for given inputs, and what a script does to its environment; the rehearsal itself is the integration test.
- **Module seam (`terraform test`).** Each new input: the architecture reaches every task definition; extra environment variables reach the services and nothing else; the database port; the KMS rotation period and the cache maintenance window left unset; the image repository address accepting the emulator's registry; the CDN's error responses appear only when given; the origin override. The demo environment's plan is unchanged by the new inputs' defaults.
- **Static analysis.** The `local` environment passes `fmt`, `validate`, `tflint` and `checkov`, and the existing backend test accepts its state key.
- **Deploy script tests** (the existing suite with a stubbed `aws`): the registry comes from the outputs; the architecture check honours the argument; the wrapper sets the endpoint and selects `local`.
- **Rehearsal run.** `make rehearse` ending in a passing smoke check is the acceptance test, run by hand and by the on-demand workflow. `make rehearse-scale` is accepted when its timeline shows each service scale out and in. A second plan showing no changes is asserted by the wrapper.
- **Prior art.** Spec 09's module tests and the deploy scripts' tests; the smoke check is reused unchanged.

## Out of Scope

- Replacing `make dev`. The Compose stack stays the everyday development loop; the rehearsal is for infrastructure changes.
- Replacing RustFS or Mailpit with Floci in `make dev`.
- Making the rehearsal a required check on every push.
- Enforcing IAM or security groups in the emulator.
- Emulating Spot interruptions, Bedrock, or the CloudFront Function.
- Changes to Floci itself.

## Further Notes

- The [research](../tickets/23-floci-rehearsal/research/floci-findings.md) found nine things that would stop a rehearsal and seven that would break something after it. It was done by reading Floci 2.5.0's source and nothing was run, so several fixes are marked inferred there. The first ticket should be a spike that gets `terraform apply` through and corrects this spec where the emulator behaves differently.
- Two findings no longer apply after spec 22: the interface endpoints are gone, and worker scaling uses queue depth, which the emulator reports.
- The spike (ticket 23-01) found the emulator accepts the ECS task protection API but has no ECS agent endpoint, so tasks get no `ECS_AGENT_URI` and the scale-in protection adapter is a no-op in `local`, as it is in `make dev`. Fargate Spot strategies are stored and honoured as records.
- The emulator moves quickly: an issue the research depended on was opened the day it was written. Pinning the version is what keeps the rehearsal stable.
- Measured in the spike: the API with its local models takes about 2.3 GB, one general worker process ingesting about 2.3 GB, one runs process about 2.35 GB; the emulator and its database, cache and registry about 0.2 GB. At the AWS settings the stack needs about 12.5 GB, so `local` runs each pool with one job per task at 1 vCPU / 3 GB, and the API at 3 GB (its AWS size, 1 GB, is below what its models take: ticket 22-09 checks this on AWS). The whole stack then peaks at about 8 GB.
