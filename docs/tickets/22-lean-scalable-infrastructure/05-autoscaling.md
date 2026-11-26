# 05: Autoscaling

**Ticket:** `22-05` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The API scales between one and three tasks on CPU, both worker pools scale on how many jobs their queue holds, and the runs pool scales to zero when it has none.

**Blocked by:**
- `22-04`

**Status:** ready-for-agent

- [ ] Application Auto Scaling targets for `api`, `worker-general` and `worker-runs`; every minimum, maximum, target and cooldown is a variable
- [ ] Defaults: `api` 1 to 3, `worker-general` 1 to 3, `worker-runs` 0 to 2, `beat` fixed at 1
- [ ] `api` uses target tracking on average CPU
- [ ] Workers scale on their queue's waiting plus in-flight messages, so a pool never scales in under a running job
- [ ] `worker-runs` goes from zero to one when its queue holds anything and back to zero after it has been empty for several minutes; above one task, both pools track waiting messages per task
- [ ] Terraform sets each service's task count at creation and ignores it afterwards, so an apply doesn't undo a scale-out
- [ ] The deploy role may manage scaling targets and policies for this project's services only
- [ ] `terraform test` asserts the targets, minimums and maximums, the runs pool's zero minimum, the metric each policy uses and that the task count is ignored
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
