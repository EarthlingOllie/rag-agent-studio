# 06: Scaling and deploys never cut a job short

**Ticket:** `22-06` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** A worker holding a job is protected from scale-in until the job ends, and a deploy waits up to 30 minutes for running jobs before it stops them.

**Blocked by:**
- `22-04`

**Status:** ready-for-agent

- [ ] A Scale-in protection port: the production adapter calls the ECS task-protection endpoint, the fake records calls, and a no-op adapter is used where there is no ECS (local, tests)
- [ ] The job reliability module sets protection when a job is claimed, renews it with the heartbeat and clears it when the job finishes, fails or is abandoned
- [ ] Protection carries an expiry a few minutes ahead, so a dead worker is never protected for ever
- [ ] A failure to set or clear protection is logged and never fails the job
- [ ] Worker task roles may set protection on their own task only
- [ ] After starting a roll, the deploy script waits up to 30 minutes for protected tasks, then clears protection on the old tasks and lets the roll complete; the limit is an argument
- [ ] The deploy role may read and clear task protection in this project's cluster only
- [ ] Task-seam tests with the fake assert protect, renew and release, including when the job fails
- [ ] The deploy scripts' tests cover the wait and clearing protection after it
- [ ] The fake is listed with the other ports in the shared test seams
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
