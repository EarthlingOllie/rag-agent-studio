# 05: Project frame

**Ticket:** `11-05` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Inside a Project, the breadcrumb's Project and section switchers replace the Project tabs, and the Project page opens with a page header whose rare actions live in a ⋯ menu.

**Blocked by:**
- [11-04: Shell, breadcrumb and navigation test helpers](04-shell-navigation.md)

**Status:** in-progress

- [ ] The Project crumb lists the Projects plus All Projects; the section crumb lists Documents, Instructions, Agents, Conversations, Analytics and Settings with icons and number hints
- [ ] The Project tab row and the All Projects link are gone
- [ ] `PageHeader` shows the name and description with Edit details and a ⋯ menu holding Archive and permanent deletion; confirmations use `ConfirmDialog`
- [ ] The Embedding Model setting moves into the Project's Settings section
- [ ] Not-found and loading states use `EmptyState` and `Skeleton`
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
