# 06: Live score drop alert

**Ticket:** `15-06` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** Owners are emailed, and the Studio shows a "Live score drop" badge, when a newly Live Version's Live score is clearly lower than the previous Live Version's.

**Blocked by:**
- [15-05: Live score](05-live-score.md)

**Status:** ready-for-agent

- [ ] The hourly alerts step, after the rollup and beside the Block rate check, checks every Agent whose Live Version has at least 30 judged Live Verdicts since it became Live against the previous Live Version in Live History over its last 30 days as Live
- [ ] The alert is raised when a one-sided pooled two-proportion test at 95% finds the new Live score lower and the drop is at least 5 percentage points; never when the previous Version has fewer than 30 judged Live Verdicts or there is none
- [ ] Raising it sets the Agent's flag and the Version it was raised against, and emails every Owner once, linking to the Version comparison of the two Versions and to the Conversations viewer filtered to the Agent's failed Live Verdicts
- [ ] The flag clears when a later check no longer finds the drop, or when the Live Version changes by publish, revert or Bulk operation; a later drop alerts again
- [ ] The Agent list and Agent read include the flag; the Studio shows the "Live score drop" badge on the Agent list and the Agent page using the existing badge mechanism
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
