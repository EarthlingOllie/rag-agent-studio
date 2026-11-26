# 02: Module inputs for a local environment

**Ticket:** `23-02` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** The modules gain the few inputs a local environment needs to differ from the demo, so no module ever branches on "is this local". The demo environment's plan is unchanged.

**Blocked by:**
- `23-01`

**Status:** ready-for-agent

- [ ] Compute: the CPU architecture of every task definition, and extra environment variables for the services
- [ ] Database: the port and the storage type
- [ ] CDN: optional custom error responses, the distribution's domain as an output, and the origin's address as an input the environment can override
- [ ] Every new input defaults to today's value; a `terraform test` asserts the demo environment's plan is the same with the defaults
- [ ] `terraform test` asserts each input reaches the resources it should and nothing else
- [ ] `make infra-check` passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
