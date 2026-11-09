# 09: Agents list and bulk actions

**Ticket:** `11-09` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** The Agents section shows each Agent with its Live state at a glance, bulk revert through the bulk bar, and creating an Agent from the page header.

**Blocked by:**
- [11-05: Project frame](05-project-frame.md)

**Status:** done

- [x] Agents are listed in a table card with `Badge` for Live v<N>, Draft changes and Not live
- [x] Selecting Agents shows `BulkBar` with Revert; results are reported per Agent
- [x] New Agent opens from a primary button in the page header; archived Agents are behind a filter
- [x] The empty state uses `EmptyState`
- [x] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [x] The palette ratchet baseline is lowered to the new count
- [x] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [x] axe reports zero AA violations on the changed pages in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [11-09-evidence/README.md](11-09-evidence/README.md).
