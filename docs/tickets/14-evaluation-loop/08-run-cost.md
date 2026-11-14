# 08: Run Cost: estimate, actual, Organisation cost

**Ticket:** `14-08` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** Before starting, the Evaluate dialog shows an estimated Cost; each Run records what it actually cost for answers and for judging, frozen when it ran, and Owners see evaluation spend as its own column in Organisation cost.

**Blocked by:**
- [14-03: Evaluation Model, Evaluation repeats and combining results](03-evaluation-model-repeats.md)
- [14-04: Two-sided Runs](04-two-sided-runs.md)

**Status:** ready-for-agent

- [ ] The estimate is cases × sides × repeats × each side's mean Cost per reply over the last 30 days (Usage rollups for a Version, Playground Messages for the Draft), plus judging from the Evaluation Model's prices and a fixed per-judgement token allowance; with no history, the side's model prices and the same allowance are used
- [ ] The Evaluate dialog shows the estimate before starting, and it is stored on the Run
- [ ] Each answer's and judgement's Cost is computed with the existing cost function and price table at the time it ran; the Run shows actual Cost split into answers and judging, and the history list shows each Run's Cost
- [ ] A later price change doesn't move a finished Run's Cost (clock fake)
- [ ] Organisation cost gains an Evaluation column per Project and Agent line and in the total; Runs never count in Version KPIs or the Token Budget
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
