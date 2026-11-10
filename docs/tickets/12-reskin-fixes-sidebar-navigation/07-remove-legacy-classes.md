# 07: Remove the legacy BUTTON / INPUT strings

**Ticket:** `12-07` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** The last pages styled with the Projects page's old button and input strings (Agent branding among them) move onto the design system, and the old strings are deleted.

**Blocked by:**
- [12-03: Projects list reskin](03-projects-list-reskin.md)
- [12-04: Organisation cost reskin](04-organisation-cost-reskin.md)
- [12-06: Project Settings reskin and Embedding Model dialog](06-project-settings-reskin.md)

**Status:** ready-for-agent

- [ ] Agent branding and any remaining importer use the design system's button and field recipes
- [ ] The Projects page no longer exports its BUTTON and INPUT strings, and nothing in the Studio defines its own button or input class string
- [ ] Agent branding is checked in both Appearances, wide and narrow
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
