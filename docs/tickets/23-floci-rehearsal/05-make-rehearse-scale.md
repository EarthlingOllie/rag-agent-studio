# 05: `make rehearse-scale`

**Ticket:** `23-05` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** A developer watches both worker pools and the API scale out and back in on a laptop.

**Blocked by:**
- `23-04`

**Status:** ready-for-agent

- [ ] `make rehearse-scale` queues a batch of ingestion jobs and starts an Evaluation Run through the API of a seeded rehearsal
- [ ] The general pool scales out and back on its queue's depth, which the emulator reports itself
- [ ] The runs pool starts from zero for the Run and returns to zero
- [ ] The command publishes a CPU figure for the API service to the emulator's CloudWatch and the API scales out and back
- [ ] It prints the same timeline as the scaling demonstration script and exits non-zero if a service never scaled
- [ ] `local` uses short cooldowns and a worker size that fits a 16 GB laptop
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
