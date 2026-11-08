# 08: Agent page and its four views

**Ticket:** `11-08` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Each Agent has four views in the breadcrumb (Playground, Versions, Embed & limits, Conversations), matching the approved mockups: Playground in the main column with configuration in collapsible sections, a Versions timeline with compare, and Embed & limits as cards.

**Blocked by:**
- [11-05: Project frame](05-project-frame.md)

**Before starting:** the round-2 design choices in spec 11's *Pending sign-off* note must be confirmed by the user.

**Status:** ready-for-agent

- [ ] The Agent crumb switches Agent; a view crumb switches between Playground, Versions, Embed & limits and Conversations
- [ ] Saved state, History and Publish sit in the top bar; Live, Draft and Not live use `Badge`
- [ ] Playground: messages in a centred column, the Trace folded under each answer (cited chunk in the accent colour, flagged chunks in the flag colour), the Instructions picker and composer restyled
- [ ] Configuration: Behaviour, Retrieval, Experience and Guardrails as `Section`s with mono summaries; the markdown editor keeps working
- [ ] Versions: Live History as a timeline, From/To picking, `Diff` for Instructions and settings, Revert and Start Draft from in ⋯ menus
- [ ] Embed & limits: `CodeBlock` snippet with launcher choice, Allowed Origins as an `EditableList` warning when empty, Unavailable text, Token Budget `Meter` and rate limits, Theme override for Owners
- [ ] Archive and delete use the ⋯ menu and `ConfirmDialog`
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
