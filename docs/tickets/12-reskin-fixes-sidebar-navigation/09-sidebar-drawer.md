# 09: Sidebar drawer on narrow screens

**Ticket:** `12-09` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** On a phone the sidebar becomes a drawer behind a menu button, so content gets the full width.

**Blocked by:**
- [12-08: Sidebar navigation on desktop](08-sidebar.md)

**Status:** ready-for-agent

- [ ] Below `md` the sidebar is hidden and an "Open navigation" button in the top bar opens it as a drawer
- [ ] Opening focuses the current link; focus stays inside the drawer while it is open
- [ ] Escape, a press outside or following a link closes it, and focus returns to the button
- [ ] The keyboard pass and the axe sweep include the open drawer at 390 px in both Appearances
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
