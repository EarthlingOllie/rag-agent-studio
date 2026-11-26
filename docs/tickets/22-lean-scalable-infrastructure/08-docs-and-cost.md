# 08: Docs and cost

**Ticket:** `22-08` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The documentation describes what now runs: the cost of leaving it on, how to show it scaling, and which parts of the scaled-up picture are built.

**Blocked by:**
- `22-05`

**Status:** ready-for-agent

- [ ] The deploy guide's expected cost table is recomputed for the new shape, for always on and for one day, with the runs pool idle
- [ ] The deploy guide gains a "showing it scale" section that says how to run the scaling script and what its timeline means
- [ ] The README's architecture diagram, stack table and deploy summary show SQS and the two worker pools
- [ ] The development guide describes the job queues and which jobs go to which
- [ ] The infrastructure map's scaled-up view marks each row as a variable today or as future work, and its "decided" note links here
- [ ] `make link-check` passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
