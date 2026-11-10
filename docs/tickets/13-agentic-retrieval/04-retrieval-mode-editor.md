# 04: Retrieval Mode and Search limit in the Agent editor

**Ticket:** `13-04` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** An Editor chooses an Agent's Retrieval Mode and Search limit in the Draft's Retrieval section, with the trade-off explained, and picks a model that supports Agentic mode.

**Blocked by:**
- [13-01: Agentic tracer](01-agentic-tracer.md)

**Status:** ready-for-agent

- [ ] The Retrieval section has a segmented control for Automatic and Agentic, with a one-sentence accuracy against cost explanation
- [ ] The Search limit field shows only in Agentic mode, validates 1–5 and autosaves
- [ ] The server's refusal (model without tool support) is shown on the field
- [ ] The model picker marks models that support tools
- [ ] Retrieval Mode and Search limit changes appear in Draft Diffs and Audit Events
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
