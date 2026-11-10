# 11: Plain breadcrumb, account menu cleanup and docs

**Ticket:** `12-11` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** The breadcrumb becomes a plain path of links, the account menu is the single home of Profile, Security and Sign out, and the docs describe the sidebar.

**Blocked by:**
- [12-08: Sidebar navigation on desktop](08-sidebar.md)
- [12-09: Sidebar drawer on narrow screens](09-sidebar-drawer.md)
- [12-10: Agent view tabs](10-agent-view-tabs.md)

**Status:** done

- [x] The breadcrumb's crumbs are plain links with no menus; the current crumb is marked `aria-current="page"`
- [x] Below `md` the breadcrumb shows only its last two crumbs; the "…" fold is gone
- [x] Profile, Security and Sign out are only in the account menu; the 1–6 number hints are gone
- [x] Draft ADR-0014 moves into `docs/adr/`; the design README's principle 3, navigation table and breadcrumb section describe the sidebar
- [x] GLOSSARY: Breadcrumb is a plain path; Breadcrumb fold and Crumb switcher are removed; Sidebar and Sidebar drawer are added
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
