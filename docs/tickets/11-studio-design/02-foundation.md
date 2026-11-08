# 02: Foundation: tokens, fonts and Appearance

**Ticket:** `11-02` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** The Studio loads the design tokens and fonts, and Members get a light or dark Appearance that follows the system until they choose, with no other visible change.

**Blocked by:**
- [11-01: Palette ratchet and design system round 2](01-ratchet-design-system-round-2.md)

**Status:** ready-for-agent

- [ ] `index.css` imports `design/tokens.css`; `index.html` loads Instrument Sans and IBM Plex Mono
- [ ] `initAppearance()` runs before the first render, so no page flashes the other Appearance
- [ ] The page background, text colour and focus ring come from tokens; the markdown styles in `index.css` use tokens
- [ ] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [ ] The palette ratchet baseline is lowered to the new count
- [ ] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [ ] axe reports zero AA violations on the changed pages in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
