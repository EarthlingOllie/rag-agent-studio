# 11: Plain breadcrumb, account menu cleanup and docs

**Ticket:** `12-11` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** The breadcrumb becomes a plain path of links, the account menu is the single home of Profile, Security and Sign out, and the docs describe the sidebar.

**Blocked by:**
- [12-08: Sidebar navigation on desktop](08-sidebar.md)
- [12-09: Sidebar drawer on narrow screens](09-sidebar-drawer.md)
- [12-10: Agent view tabs](10-agent-view-tabs.md)

**Status:** ready-for-agent

- [ ] The breadcrumb's crumbs are plain links with no menus; the current crumb is marked `aria-current="page"`
- [ ] Below `md` the breadcrumb shows only its last two crumbs; the "…" fold is gone
- [ ] Profile, Security and Sign out are only in the account menu; the 1–6 number hints are gone
- [ ] Draft ADR-0014 moves into `docs/adr/`; the design README's principle 3, navigation table and breadcrumb section describe the sidebar
- [ ] GLOSSARY: Breadcrumb is a plain path; Breadcrumb fold and Crumb switcher are removed; Sidebar and Sidebar drawer are added
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
