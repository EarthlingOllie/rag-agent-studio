# 10: Rollout evaluation

**Ticket:** `14-10` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** In the Bulk publish rollout dialog, an Editor starts a Rollout evaluation that runs, for each selected Agent with an Evaluation Set, the Live Version against its configuration answering with the new Instructions Version, and sees each Agent's Regressions before rolling out.

**Blocked by:**
- [14-09: Evaluation in the Publish dialog](09-publish-dialog-evaluation.md)

**Status:** ready-for-agent

- [ ] Starting a Rollout evaluation creates one Run per selected Agent with an Evaluation Set (kind `rollout`): first side the Live Version, second side the Live configuration answering with the new Instructions Version; Agents without a set are skipped
- [ ] Rollout sides can't be created through the general Run API
- [ ] A read returns each selected Agent's state: Regressions, not evaluated, running or clear
- [ ] The rollout dialog shows an Evaluate rollout action and a per-Agent evaluation column; Agents with Regressions are warned about, never deselected or blocked
- [ ] Rollout Runs appear in each Agent's Run history
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
