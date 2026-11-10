# 02: Project details dialog (New Project and Edit details)

**Ticket:** `12-02` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** A Member creates a Project and edits a Project's name and description in one dialog, instead of inline forms that push the page around.

**Blocked by:**
- None

**Status:** in-progress

- [ ] Edit details opens a "Project details" dialog with the current name and description; Save closes it, the header shows the new values and a toast confirms
- [ ] The Edit details button stays in the Project header while the dialog is open; nothing renders inline under the header
- [ ] New Project opens the same dialog in create mode (Name required, Description); Create Project opens the new Project
- [ ] A refusal (such as a duplicate name) shows inside the dialog and keeps what was typed
- [ ] Cancel and Escape close the dialog without saving, and focus returns to the button that opened it
- [ ] The dialog's fields use the design system's field recipes
- [ ] Until 12-03 places it in the header, New Project is a button where the inline form was; the inline New Project form is removed
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
