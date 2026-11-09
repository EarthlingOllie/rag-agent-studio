# 11: Organisation settings

**Ticket:** `11-11` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Organisation settings use a Settings switcher crumb instead of tabs, and General, Members, Credentials, Models, Theme and Audit follow the system; the Theme preview keeps showing the Organisation's Theme.

**Blocked by:**
- [11-04: Shell, breadcrumb and navigation test helpers](04-shell-navigation.md)

**Status:** done

- [x] The Settings crumb lists General, Credentials, Models, Theme, and Members and Audit for Owners only
- [x] Forms sit in panels with labels above fields and one primary per form; the price table and audit log use table cards with `Pagination`
- [x] Credentials show checks with `Badge` and deletes with `ConfirmDialog`; invites and member changes confirm with `Toast`
- [x] The Theme editor's form is reskinned; the widget preview (`packages/ui`) is untouched
- [x] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [x] The palette ratchet baseline is lowered to the new count
- [x] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [x] axe reports zero AA violations on the changed pages in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [11-11-evidence/README.md](11-11-evidence/README.md).
