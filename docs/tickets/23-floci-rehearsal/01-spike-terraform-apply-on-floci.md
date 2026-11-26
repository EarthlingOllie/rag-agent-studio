# 01: Spike: get `terraform apply` through on Floci

**Ticket:** `23-01` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** A throwaway run that applies the demo modules to Floci and records what really blocks it, so the rest of this spec is built on what the emulator does and not on what its source suggested.

**Blocked by:**
- `22-05`

**Status:** ready-for-agent

- [ ] Floci runs with the Docker socket mounted and `terraform apply` of the demo modules reaches the end, with every workaround written down
- [ ] Each of the research's nine blockers is marked confirmed, wrong or changed, with the fix that worked
- [ ] Whether the emulator supports ECS task protection, Fargate Spot strategies and scaling on SQS queue depth is recorded
- [ ] The memory the whole stack needs, and the worker size that fits a 16 GB laptop, are measured
- [ ] Spec 23 and the research file are corrected where the emulator behaved differently; tickets 23-02 to 23-06 are adjusted if the spike changes their scope
- [ ] No spike code is merged except the corrected documents
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
