# 05: Interrupted Evaluation Runs

**Ticket:** `21-05` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** An Evaluation Run whose worker died becomes Interrupted within minutes: it keeps the answers and Cost it has, frees the Agent, and the Editor can run it again.

**Blocked by:**
- `21-02`
- `21-03`

**Status:** ready-for-agent

- [ ] Evaluation Runs gain a heartbeat, written while the Run works and at each answer
- [ ] A Run with no heartbeat for 5 minutes is ended by the sweeper as `interrupted`, a new finished status beside completed, failed and cancelled
- [ ] A Run is never marked Interrupted while its worker is alive, however long it takes; a second delivery of its job does nothing and pays for no answer
- [ ] An Interrupted Run keeps its answers, Verdicts and Cost so far, and frees the Agent for another Run or Suggestion run
- [ ] Reads that mean "latest result", the Evaluation summary, the Publish warning and Suggestion evidence treat an Interrupted Run as they treat a cancelled one
- [ ] A Run Queued for more than 15 minutes is re-sent, including the Runs of a Rollout evaluation that were never queued because the API died partway through
- [ ] Run history and the Run page show Interrupted with a one-line explanation and its partial results
- [ ] "Run again" on an Interrupted Run starts a new Run with the same sides, after the usual estimated Cost
- [ ] Runs already stuck on Running when this ships become Interrupted on the first sweep
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
