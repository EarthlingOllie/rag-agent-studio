# 06: End-to-end and live suite

**Ticket:** `19-06` · **Spec:** [Judging guidance](../../specs/19-judging-guidance-spec.md)

**What to build:** End-to-end tests draft, check and save guidance on the seeded stack, and a nightly live run drafts and checks with a real provider.

**Blocked by:**
- [18-06: Demo seed and end-to-end](../18-verdict-review/06-demo-seed-e2e.md)
- [19-02: Comparisons by Judging setup](./02-comparisons-by-judging-setup.md)
- [19-05: Draft guidance from disagreements](./05-draft-guidance.md)

**Status:** ready-for-agent

- [ ] End-to-end on the seeded stack with enough sample reviews: draft guidance with the fake judge, check it and see agreement rise, save it, and see the new Judging setup in the next Run's header
- [ ] The axe checks cover the guidance card and the draft and check states
- [ ] Live suite: one real-provider draft and check over a small seeded set of reviews, run nightly outside the coverage gate
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
