# 03: Colour codemod

**Ticket:** `11-03` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Every Studio page uses design tokens instead of Tailwind palette colours, so both Appearances work everywhere, without any change to markup or behaviour.

**Blocked by:**
- [11-02: Foundation: tokens, fonts and Appearance](02-foundation.md)

**Status:** in-progress

- [ ] A one-off script applies the class-mapping table from the `studio-reskin` skill across `apps/studio/src`; it is committed with the PR and then deleted
- [ ] Only class lists change: no markup, text, routes or tests change
- [ ] Ambiguous mappings are left for review and listed in the PR
- [ ] The palette count falls substantially; anything left is listed by file for the area tickets
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
