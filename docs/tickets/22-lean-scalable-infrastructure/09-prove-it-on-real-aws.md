# 09: Prove it on real AWS

**Ticket:** `22-09` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The repository owner deploys the new shape to AWS, seeds it, runs the scaling script and destroys it, and the evidence shows Spot, autoscaling, task protection and the missing endpoints working together.

**Blocked by:**
- `22-06`
- `22-07`
- `22-08`

**Status:** ready-for-human

- [ ] The deploy workflow succeeds from a clean account state and the smoke check passes
- [ ] The seed workflow succeeds and the demo Owner can sign in
- [ ] The scaling script's timeline shows `api`, `worker-general` and `worker-runs` each scale out and return to their minimum, with the runs pool at zero before and after
- [ ] The cold start of the runs pool, from a Run being queued to its first answer, is measured and recorded
- [ ] A deploy started while an Evaluation Run is in progress waits for it
- [ ] If a Spot task is reclaimed during the run, the evidence notes how its Document recovered
- [ ] The destroy workflow leaves nothing but the bootstrap's state bucket and deploy role
- [ ] The evidence folder holds the timeline, the workflow run links and the day's AWS cost; the deploy guide's cost table is corrected if the bill disagrees
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
