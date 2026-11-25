# 02: Comparisons by Judging setup

**Ticket:** `19-02` · **Spec:** [Judging guidance](../../specs/19-judging-guidance-spec.md)

**What to build:** Saving guidance can't raise a false Live score drop alert, and the Version comparison, Time series and Publish dialog say when judgements were made under different Judging setups.

**Blocked by:**
- [19-01: Judging guidance tracer: save it, judge with it, record the Judging setup](./01-judging-guidance-tracer.md)

**Status:** ready-for-agent

- [ ] The Live score drop alert compares the Live Version's and the previous Live Version's Live Verdicts under the current Judging setup only; with fewer than 30 under it for the previous Version, there is no alert
- [ ] A test shows saving guidance mid-way never raises the alert
- [ ] The Version comparison and Time series responses list Judging setup changes in their range; the Studio shows a note in the Confounder note's style and a Time series marker where it changed
- [ ] The Publish summary gains a notice when the Draft's latest Run was judged under an earlier Judging setup; it never blocks
- [ ] The guidance card says, before saving, that a new Judging setup restarts agreement and quiets the drop alert for the previous Live Version
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
