# 02: Live Verdict context, errors and retention

**Ticket:** `15-02` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** The judge sees a follow-up in its context, never sees the system prompt, and copes with failure; Live Verdict reasons are Purged with their Message while their outcomes stay.

**Blocked by:**
- [15-01: Live Verdict tracer: sample a reply and judge it](01-live-verdict-tracer.md)

**Status:** ready-for-agent

- [ ] The judge is given the reply's Remembered turns as a spotlighted, delimited data block with escaped delimiters; the system prompt and Project Instructions are never sent (spec 14's prompt contract test extended to show both)
- [ ] A judge error or timeout makes the Live Verdict `error` with its reason, with no retry
- [ ] A Message, or any of its Remembered turns, Purged before judging makes the Live Verdict `skipped`, and nothing is sent to the judge
- [ ] The Purge clears a Live Verdict's reasons and stamps it purged-at in the same pass as its Message; outcomes, Cost and counts stay
- [ ] Deleting a Conversation clears its Live Verdicts' reasons at once through the same path
- [ ] The Trace shows error, skipped and "Text purged" states
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
