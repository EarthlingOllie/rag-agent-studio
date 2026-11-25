# 04: Reviewing where Verdicts are shown

**Ticket:** `18-04` · **Spec:** [Verdict review](../../specs/18-verdict-review-spec.md)

**What to build:** An Editor agrees or disagrees with a judged Verdict in Run detail or a Live Verdict check in the Trace, with a reason when disagreeing; the review is shown on the Verdict and can be replaced or removed.

**Blocked by:**
- [18-02: Verdict review tracer: blind Review sample of Run Verdicts](./02-verdict-review-tracer.md)
- [18-03: Live Verdict checks in the Review sample, and retention](./03-live-verdicts-in-sample-retention.md)

**Status:** ready-for-agent

- [ ] Put and delete a review on a judged Evaluation Verdict and on a Live Verdict check; these store `from_sample` false
- [ ] Run results and the Trace payload carry each judged Verdict's or check's review (outcome, reason or "Text purged", who, when, from_sample)
- [ ] Run detail and the Trace's Live Verdict section show Agree and Disagree, a reason field on Disagree, and the existing review with who, when and "from the Review sample"
- [ ] A review given here takes its target out of the Review sample pool
- [ ] Replacing a sample review here makes it `from_sample` false, so it stops counting towards agreement
- [ ] Removing a review puts the target back in the pool
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
