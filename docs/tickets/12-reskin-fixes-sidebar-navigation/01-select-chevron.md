# 01: Dropdown chevron token and base rule

**Ticket:** `12-01` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** Every dropdown in the Studio shows the design system's chevron, inset from the right edge to mirror the text's left inset, visible in both Appearances; option text never runs under it and a disabled dropdown dims it.

**Blocked by:**
- None

**Status:** in-progress

- [ ] Every single-value select (form fields, toolbar pills, table cells) draws the design system's chevron-down instead of the browser's arrow
- [ ] The chevron sits as far from the right edge as the text sits from the left, and a select reserves at least 36 px on the right so long option text never runs under it
- [ ] The chevron colour comes from a new token with light, system-dark and chosen-dark values; it is visible against the field in both Appearances
- [ ] A disabled select dims its chevron along with the field
- [ ] The `field` recipes gain a compact select for table cells; no page keeps its own select class string (Members' role select, the Audit filters and the Draft editor move onto recipes)
- [ ] The token contract test checks the chevron token is declared in all three blocks and that system-dark and chosen-dark match
- [ ] An end-to-end check finds a select's computed `appearance` is `none` and its right padding is at least 36 px
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
