# 05: Seed in AWS

**Ticket:** `10-05` · **Spec:** [Seed data and showcase](../../specs/10-seed-showcase-spec.md)

**What to build:** The deployed demo environment can be seeded with the same demo data through a one-off ECS task.

**Blocked by:**
- [10-02: Seeded history](02-seeded-history.md)
- [09-06: Demo environment and deploy workflow](../09-terraform-deploy/06-demo-env-deploy.md)

**Status:** ready-for-agent

- [ ] A workflow dispatch runs the seed as a one-off ECS task
- [ ] Running it again is idempotent
- [ ] The steps are documented in the README
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
