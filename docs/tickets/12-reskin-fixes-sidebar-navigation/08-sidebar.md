# 08: Sidebar navigation on desktop

**Ticket:** `12-08` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** Every place a Member can go is a visible link in a sidebar: the Organisation switcher, the Organisation's pages and, inside a Project, its switcher and sections.

**Blocked by:**
- None

**Status:** in-progress

- [ ] First, the shared navigation helpers (Playwright and Testing Library) learn to follow sidebar links, keeping their names and menu vocabulary so existing specs change little
- [ ] The sidebar is a navigation landmark named "Studio": the Organisation switcher (plain text for a Member of one Organisation), then Projects, Cost (Owners only) and Settings
- [ ] Inside a Project it adds the Project switcher (open Projects, then All Projects) and Documents, Instructions, Agents, Conversations, Analytics and Settings
- [ ] The current link has the soft accent fill and `aria-current="page"`, and stays current on inner pages (the Document viewer under Documents, an Agent under Agents, a Conversation under Conversations)
- [ ] Under the Require MFA policy the sidebar offers only Security until the Member enrols
- [ ] Main content keeps its 1160 px maximum, centred beside a fixed sidebar of about 240 px
- [ ] The breadcrumb's switcher menus still work; the end-to-end specs move to the sidebar and stay green
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
