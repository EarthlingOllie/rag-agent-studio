# 04: Shell, breadcrumb and navigation test helpers

**Ticket:** `11-04` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** One top bar replaces the header and side menu: its breadcrumb carries the Organisation, section and item, every level with siblings is a switcher, and the account menu holds Profile and Sign out. Every test that clicked a tab or side link now uses shared helpers.

**Blocked by:**
- [11-03: Colour codemod](03-colour-codemod.md)

**Status:** ready-for-agent

- [ ] `OrganisationShell` renders `TopBar` with the mark, the breadcrumb, the Appearance toggle and the account menu; the side menu is gone
- [ ] The Organisation crumb switches Organisation (with today's error handling); the org-level section switcher offers Projects, Settings and Security, and only Security while MFA enrolment is required
- [ ] The breadcrumb is computed from the route; the current crumb is in the accent colour with `aria-current="page"`, and each switcher's name is "<label>, <what it holds>"
- [ ] Switcher items that navigate are router links
- [ ] `openSection` helpers exist for Playwright (`e2e/fixtures/navigation.ts`) and Testing Library (`apps/studio/src/test/navigation.ts`), and every navigation step in unit and end-to-end tests uses them
- [ ] Role-based hiding is asserted as a missing menu item
- [ ] `candidate` is merged immediately before landing; no other design ticket is open while this one is
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
