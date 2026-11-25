# 06: Demo seed and end-to-end

**Ticket:** `18-06` · **Spec:** [Verdict review](../../specs/18-verdict-review-spec.md)

**What to build:** The demo Organisation's agreement card shows about 40 seeded Review sample reviews with a few false passes, and an end-to-end test reviews an item and sees agreement move.

**Blocked by:**
- [18-03: Live Verdict checks in the Review sample, and retention](./03-live-verdicts-in-sample-retention.md)
- [18-04: Reviewing where Verdicts are shown](./04-reviewing-where-shown.md)
- [18-05: Evaluation Model agreement card](./05-agreement-card.md)

**Status:** ready-for-agent

- [ ] The seed submits about 40 Review sample reviews through the API (ADR-0012) across the HR helper's Run Verdicts and Live Verdicts, a few of them false passes with reasons
- [ ] Seed tests check the seeded reviews and that agreement shows false passes
- [ ] End-to-end on the seeded stack: open the Review sample, review an item, see the reveal, and see the agreement count go up
- [ ] End-to-end: disagree with a Verdict in Run detail and see the review on it
- [ ] The axe checks cover the Review sample page and the agreement card
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
