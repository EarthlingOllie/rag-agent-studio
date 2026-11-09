# 06: README and automated demo

**Ticket:** `10-06` · **Spec:** [Seed data and showcase](../../specs/10-seed-showcase-spec.md)

**What to build:** A reviewer opens the README and understands the product, architecture and decisions in minutes. The five-minute interview demo is automated as a single Playwright test.

**Blocked by:**
- [10-03: Demo host pages](03-demo-host-pages.md)
- [10-04: Attack panel](04-attack-panel.md)

**Status:** done

Evidence: [10-06-evidence](10-06-evidence/README.md)

- [x] The README has the pitch, a Mermaid architecture diagram, the stack, a quickstart, testing and security sections, deploy and destroy instructions with cost, and links to the glossary, ADRs, plan, specs and tickets
- [x] The five-minute demo script is in the README, with CI and coverage badges
- [x] A link-check CI job verifies every relative link
- [x] The whole demo runs as one Playwright test
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
