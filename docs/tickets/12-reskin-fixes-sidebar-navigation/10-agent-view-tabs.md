# 10: Agent view tabs

**Ticket:** `12-10` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** An Agent's views are visible tabs under its name, and an Agent page has one heading instead of three stacked headers.

**Blocked by:**
- [12-08: Sidebar navigation on desktop](08-sidebar.md)

**Status:** ready-for-agent

- [ ] Playground, Versions, Embed & limits and Conversations are a tab row under the Agent's header; the current one is marked, and stays marked on a Conversation opened from it
- [ ] The Agent's name carries a ▾ that switches to another of the Project's Agents
- [ ] Agent pages no longer show the Project's page header; the Agent's name is the page's h1
- [ ] The navigation helpers read Agent views from the tab row
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
