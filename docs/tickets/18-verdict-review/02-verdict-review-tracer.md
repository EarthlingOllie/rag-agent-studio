# 02: Verdict review tracer: blind Review sample of Run Verdicts

**Ticket:** `18-02` · **Spec:** [Verdict review](../../specs/18-verdict-review-spec.md)

**What to build:** An Editor opens the Review sample, is shown a judged Evaluation Run Verdict without the Evaluation Model's outcome, gives their own pass or fail, then sees the Evaluation Model's pass or fail and reason; Organisation settings › Models shows how many sample reviews agreed.

**Blocked by:**
- [18-01: Prefactor: rebuild a judgement's input from what was stored](./01-prefactor-judge-input.md)

**Status:** ready-for-agent

- [ ] A Verdict review row: target Evaluation Verdict (unique), the Editor's outcome, the Evaluation Model's outcome and the check kind copied, the Evaluation Model copied, `from_sample`, an optional reason (up to 1,000 characters), reviewed_by, reviewed_at, Agent and Organisation
- [ ] The pool is every judged Reference answer and grounding Verdict (outcome pass or fail) by the Organisation's current Evaluation Model with no review; Expected source, Expect Fallback Text, Stale and Error Verdicts are never in it
- [ ] `next` draws uniformly at random from the pool (seeded through test settings) and returns the rebuilt judge input from 18-01 (question, Reference answer when that is the check, answer, Chunks with cited flags) and never the Evaluation Model's outcome or reason
- [ ] Submitting stores the review with `from_sample` true and returns the Evaluation Model's outcome and reason; a later review of the same target replaces the earlier one; Skip stores nothing
- [ ] Reviews never change a Verdict, the Evaluation score, Regressions or the Publish summary (test with and without reviews), per [ADR-0018](../../adr/0018-reviews-measure-guidance-changes.md)
- [ ] An Organisation-level Review sample page: the item, Pass and Fail, Skip, the reveal, the reason field when the Editor differed, Next, and an empty state
- [ ] Organisation settings › Models shows "x of y sample reviews agreed" for the current Evaluation Model, with a link to the Review sample
- [ ] Editors and Owners review; every Member reads; another Organisation's reviews and pool are unreachable
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
