# 06: Documents and Document viewer

**Ticket:** `11-06` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** The Documents section matches the approved mockup: stat cards, a toolbar with search, Tag chips and status filter, one Upload primary, a table with ⋯ row menus, and a quiet drop zone; the Document viewer follows the same system.

**Blocked by:**
- [11-05: Project frame](05-project-frame.md)

**Status:** ready-for-agent

- [ ] Stat cards show Documents against the quota, Chunks, flagged chunks (flag colour when above zero) and the Embedding Model
- [ ] Rows show the file type, `Tag`, `Status` and `FlagCount`; Retry, New edition, Edit Tags and Delete move into a ⋯ menu
- [ ] The Tags panel opens from Manage tags; bulk selection uses `BulkBar`
- [ ] Upload, ingestion failures and limits use `Notice`, `Toast` and `ConfirmDialog`
- [ ] The Document viewer shows the document crumb, the markdown and paged chunks on cards, with flagged chunks badged
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
