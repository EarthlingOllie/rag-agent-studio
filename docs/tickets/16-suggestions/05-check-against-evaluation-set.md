# 05: The check against the Evaluation Set

**Ticket:** `16-05` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** When a Suggestion changes the configuration and the Agent has an Evaluation Set, the run checks the Suggestion against the Live Version, and the Suggestion shows both Evaluation scores and any Regressions.

**Blocked by:**
- [16-02: Suggestion tracer: failed Live Verdicts become a system prompt Suggestion](02-suggestion-tracer.md)
- [16-04: Suggestion run dialog, Cost and lifecycle](04-run-dialog-cost-lifecycle.md)

**Status:** done

- [x] Evaluation Runs gain kind `suggestion` and Run sides gain kind `suggestion`: the base AgentConfig with the suggested changes, answering with the Live Version's pinned Instructions; it is created only by a Suggestion run, never through the general Run API
- [x] The check's first side is the Live Version and its second the Suggestion; there is no check for a `gaps_only` or `no_change` outcome, and a Suggestion on an Agent with no Evaluation Set is marked "Not checked"
- [x] The Suggestion links its check Run and shows both Evaluation scores and each Regression with its Verdicts' reasons; a failed check is a warning only
- [x] Actual checking Cost is frozen and shown with proposing Cost
- [x] The check Run appears in the Agent's Run history labelled as a Suggestion's check, and never counts in the Evaluation summary
- [x] Cancelling the Suggestion cancels its check Run
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
