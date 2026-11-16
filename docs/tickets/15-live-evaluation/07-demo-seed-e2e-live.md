# 07: Demo seed, end-to-end and live suite

**Ticket:** `15-07` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** The Demo Organisation shows v2's lower Live score next to v1's, an end-to-end test walks from a sampled widget reply to an Evaluation Case, and a nightly live Live Verdict proves real judging works.

**Blocked by:**
- [15-02: Live Verdict context, errors and retention](02-live-verdict-context-errors-retention.md)
- [15-03: Evaluation budget](03-evaluation-budget.md)
- [15-04: Live Verdicts in the Conversations viewer](04-live-verdicts-conversations-viewer.md)
- [15-05: Live score](05-live-score.md)

**Status:** ready-for-agent

- [ ] The seed sets the Demo Organisation an Evaluation budget and the HR helper a Live sample rate, and plays Live Verdicts for v1's and v2's seeded Visitor replies through the normal sampling path under the seed clock (ADR-0012)
- [ ] v2's uncited replies fail grounding, so its Live score is clearly lower than v1's in the Version comparison and the Time series
- [ ] No standing Live score drop alert is faked on the current Live Version
- [ ] Seed tests check the HR helper's Live Verdicts and that v2's Live score is lower than v1's
- [ ] End-to-end: on the seeded stack, set the HR helper's Live sample rate to 100%, send a widget message, see its Live Verdict in the Conversations viewer's Trace, filter to failed replies and add one to the Evaluation Set; axe checks cover the Trace section and Organisation settings
- [ ] Live suite: one real-provider Live Verdict of a seeded reply, run nightly outside the coverage gate
- [ ] `docs/demo.md` mentions the Live score in the Analytics comparison step
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
