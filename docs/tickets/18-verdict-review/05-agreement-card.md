# 05: Evaluation Model agreement card

**Ticket:** `18-05` · **Spec:** [Verdict review](../../specs/18-verdict-review-spec.md)

**What to build:** Organisation settings › Models shows Evaluation Model agreement in full: rate with its Wilson interval, Low sample, false passes and false fails, per check, and earlier Evaluation Models.

**Blocked by:**
- [18-02: Verdict review tracer: blind Review sample of Run Verdicts](./02-verdict-review-tracer.md)

**Status:** done

- [x] Agreement is counted when read over `from_sample` reviews of a given Evaluation Model: reviews, agreed, false passes (it passed, the Editor said fail) and false fails, overall and per check (grounding, answers the question, Reference answer)
- [x] The rate carries its Wilson interval (the existing function) and Low sample under 30 reviews
- [x] The card shows the current Evaluation Model's figures and lists earlier Evaluation Models that have reviews
- [x] The card shows how many sample reviews the Organisation and the signed-in Editor have given, and how many items were skipped
- [x] Changing the Evaluation Model starts new figures; the old ones stay listed
- [x] Every Member reads the card
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
