# 04: Organisation cost reskin

**Ticket:** `12-04` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** An Owner reads what the Organisation spent on a page that looks like the other data pages: a header, a toolbar of filters, summary cards and a table card.

**Blocked by:**
- None

**Status:** done

- [x] The page opens with a page header (Organisation cost) whose description is the existing sentence about frozen prices
- [x] "Break down by" is a segmented control (Project / Agent); From and To are date filters styled like those on Conversations and Analytics
- [x] Summary cards show the total, Visitor and Playground spend for the period; the period line sits under the toolbar
- [x] The table is a table card with amounts right-aligned in mono and the total row set apart; on a narrow screen it scrolls inside its card and the page doesn't scroll sideways
- [x] Nothing spent in the period shows a designed empty state; bad dates (From after To, more than 366 days) show the existing message as an error notice; loading shows a placeholder
- [x] Editors see a designed state saying only Owners see the Organisation's spend
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
