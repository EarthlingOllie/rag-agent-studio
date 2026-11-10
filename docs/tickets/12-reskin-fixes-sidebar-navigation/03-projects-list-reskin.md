# 03: Projects list reskin

**Ticket:** `12-03` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** The Organisation's Projects page looks like the Agents list: a header with New Project, an Active / Archived filter, a table card, and designed states.

**Blocked by:**
- [12-02: Project details dialog (New Project and Edit details)](02-project-details-dialog.md)

**Status:** done

- [x] The page opens with a page header titled Projects, a one-line description and New Project as its one primary action, top right
- [x] A segmented "Projects shown" filter (Active / Archived) replaces the Show archived Projects button; New Project is hidden while Archived is shown
- [x] Active Projects are a table card: Name (a link, no underline), Description on one line, and Documents and Agents counts right-aligned in mono
- [x] Archived Projects are a table card with the archived date; Owners restore a Project from its row and a toast confirms; Editors are told only Owners can restore
- [x] Loading shows a placeholder; failure shows an error state; no Projects and no archived Projects show designed empty states
- [x] The "is being deleted permanently" message after deleting a Project is a success notice
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
