# 06: Interrupted Suggestion runs

**Ticket:** `21-06` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A Suggestion run whose worker died never stays in progress: it fails as interrupted, or keeps the proposal the Editor already paid for as not checked. A second delivery of its job changes nothing.

**Blocked by:**
- `21-05`

**Status:** ready-for-agent

- [ ] The Suggestion run's first step claims from Queued only, so a second delivery does nothing: no evidence, proposed changes or Knowledge Base gaps are added and the proposer is not called again
- [ ] Suggestion runs gain a heartbeat that covers gathering, proposing and checking
- [ ] A stale run with no proposal stored becomes Failed with the reason `interrupted`
- [ ] A stale run with a proposal stored settles as not checked, keeps its proposing Cost, and its check Run becomes Interrupted
- [ ] Cancelling a Suggestion's check Run directly settles the Suggestion as not checked
- [ ] A Suggestion run Queued for more than 15 minutes is re-sent
- [ ] The Suggestion page shows the interrupted failure and the not-checked state with a one-line explanation
- [ ] Tests count proposer calls on the fake chat model across a second delivery and across a kill in each phase
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
