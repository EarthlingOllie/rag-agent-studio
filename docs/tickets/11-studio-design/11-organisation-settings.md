# 11: Organisation settings

**Ticket:** `11-11` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Organisation settings use a Settings switcher crumb instead of tabs, and General, Members, Credentials, Models, Theme and Audit follow the system; the Theme preview keeps showing the Organisation's Theme.

**Blocked by:**
- [11-04: Shell, breadcrumb and navigation test helpers](04-shell-navigation.md)

**Status:** in-progress

- [ ] The Settings crumb lists General, Credentials, Models, Theme, and Members and Audit for Owners only
- [ ] Forms sit in panels with labels above fields and one primary per form; the price table and audit log use table cards with `Pagination`
- [ ] Credentials show checks with `Badge` and deletes with `ConfirmDialog`; invites and member changes confirm with `Toast`
- [ ] The Theme editor's form is reskinned; the widget preview (`packages/ui`) is untouched
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
