# 13: Polish: narrow screens, accessibility and screenshots

**Ticket:** `11-13` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** The reskin is finished: no palette classes remain, the top bar works on narrow screens, the axe harness runs every page in both Appearances, and the documented screenshots show the new look.

**Blocked by:**
- [11-06: Documents and Document viewer](06-documents.md)
- [11-07: Instructions, Versions and rollout dialog](07-instructions-versions-rollout.md)
- [11-08: Agent page and its four views](08-agent-views.md)
- [11-09: Agents list and bulk actions](09-agents-list-bulk.md)
- [11-10: Conversations and Analytics](10-conversations-analytics.md)
- [11-11: Organisation settings](11-organisation-settings.md)
- [11-12: Signed-out pages, profile, security and status](12-signed-out-account-pages.md)

**Status:** in-progress

- [ ] The latest `candidate` is merged in and any feature UI it brings is reskinned, so `candidate-reskin` can merge back into `candidate` cleanly
- [ ] The palette count is zero; the ratchet becomes "none allowed" and the baseline file is deleted
- [ ] On narrow screens the breadcrumb collapses its middle crumbs into a menu and keeps the Organisation and the current page
- [ ] The axe harness runs every signed-in page in light and dark
- [ ] `docs/screenshots` is recaptured in both Appearances
- [ ] A keyboard-only pass of every switcher, menu and dialog is recorded in the evidence
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
