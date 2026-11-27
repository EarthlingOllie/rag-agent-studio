# 03: `make rehearse` reaches a passing smoke check

**Ticket:** `23-03` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** One command starts Floci, applies the same modules through a `local` environment, pushes the images, runs the migration, rolls the services, uploads the Studio and passes the existing smoke check, with no AWS account.

**Blocked by:**
- `23-02`

**Status:** ready-for-agent

- [ ] A `local` environment root composes the same modules as the demo and differs only in inputs and provider settings; its state is in a bucket in Floci with a lock file
- [ ] A rehearsal Compose file, separate from `make dev`, runs the pinned Floci with its settings in one place, each with a comment saying which emulator gap it covers; it uses port 4566 and stops `make dev`'s Floci first (23-01: a changed `FLOCI_PORT` breaks the health check and queue URLs), and pre-pulls the pgvector, Valkey and `registry:2` images, failing clearly on a Docker Hub rate limit
- [ ] The emulated database has pgvector, the cache keeps TLS and its auth token, and CloudFront's origin-facing prefix list is supplied to the emulator
- [ ] The tasks trust the emulator's CA (23-01: Floci 2.5.0 gives ECS tasks no CA bundle): the pushed image carries it and `SSL_CERT_FILE` points at it, so the cache's TLS and the HTTPS queue URLs verify
- [ ] The deploy script takes the registry address from Terraform's outputs and the expected image architecture from an argument, defaulting to today's behaviour, and logs in to the repository address's host (the emulator's `proxyEndpoint` names another host)
- [ ] A wrapper exports the emulator endpoint and test credentials, makes `000000000000.<endpoint host>` resolve to the emulator (23-01: the provider reads bucket tags through S3 Control with that host, and the apply hangs otherwise), creates the state bucket with the region's location constraint, selects `local` and calls the unchanged deploy script
- [ ] `make rehearse` ends with the smoke check passing against the emulated CloudFront address, on Intel and Apple-silicon machines
- [ ] `make rehearse-down` destroys the environment and removes Floci's containers and data; a second `make rehearse` then succeeds
- [ ] A clear message is shown when Docker socket access or memory is insufficient
- [ ] `local` sets `managed_nat`, the `X86_64` architecture on Intel hosts, the origin `localhost`, the database port 7001, and sizes from 23-01: each worker pool one job per task at 1 vCPU / 3 GB, the API 3 GB
- [ ] The deploy scripts' tests cover the registry, the architecture argument and the wrapper; the `local` environment passes `make infra-check` and the backend test accepts its state key
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
