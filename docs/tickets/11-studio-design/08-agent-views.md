# 08: Agent page and its four views

**Ticket:** `11-08` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Each Agent has four views in the breadcrumb (Playground, Versions, Embed & limits, Conversations), matching the approved mockups: Playground in the main column with configuration in collapsible sections, a Versions timeline with compare, and Embed & limits as cards.

**Blocked by:**
- [11-05: Project frame](05-project-frame.md)

**Status:** done

- [x] The Agent crumb switches Agent; a view crumb switches between Playground, Versions, Embed & limits and Conversations
- [x] Saved state, History and Publish sit in the top bar; Live, Draft and Not live use `Badge`
- [x] Playground: messages in a centred column, the Trace folded under each answer (cited chunk in the accent colour, flagged chunks in the flag colour), the Instructions picker and composer restyled
- [x] Configuration: Behaviour, Retrieval, Experience and Guardrails as `Section`s with mono summaries; the markdown editor keeps working
- [x] Versions: Live History as a timeline, From/To picking, `Diff` for Instructions and settings, Revert and Start Draft from in ⋯ menus
- [x] Embed & limits: `CodeBlock` snippet with launcher choice, Allowed Origins as an `EditableList` warning when empty, Unavailable text, Token Budget `Meter` and rate limits, Theme override for Owners
- [x] Archive and delete use the ⋯ menu and `ConfirmDialog`
- [x] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [x] The palette ratchet baseline is lowered to the new count
- [x] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [x] axe reports zero AA violations on the changed pages in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [11-08-evidence/README.md](11-08-evidence/README.md).
