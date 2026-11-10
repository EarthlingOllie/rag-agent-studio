# 08: Searches in metrics and retention

**Ticket:** `13-08` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Editors can measure what the Retrieval Mode costs and gains, and search queries expire with the Message text they came from.

**Blocked by:**
- [13-02: Agentic tracer: one Knowledge Search, end to end](02-agentic-tracer.md)

**Status:** in-progress

- [ ] Usage rollups record a search count per Agent Version per UTC day
- [ ] Version KPIs and Version comparison show mean searches per reply
- [ ] The Version list and Version Diff show the Retrieval Mode
- [ ] Playground Messages stay out of the Visitor rollups
- [ ] Purging Message text (Retention Window) also purges search queries
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
