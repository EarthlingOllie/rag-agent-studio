# 07: Guardrails in both modes

**Ticket:** `13-07` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Prompt-injection defences hold in Agentic mode, and the Attack evaluation suite proves it for both Retrieval Modes.

**Blocked by:**
- [13-04: Search limit and Fallback Text](04-search-limit-fallback.md)

**Status:** ready-for-agent

- [ ] Each search query is checked for the Canary token before it runs; a match ends the reply as a canary leak (Fallback Text and a Guardrail outcome) and the query isn't run
- [ ] Chunks returned by Knowledge Search are spotlighted and handled by Flagged Chunk mode exactly as in Automatic mode
- [ ] The Attack evaluation suite runs each attack in both Retrieval Modes; the report gives a Pass rate per mode and CI gates both
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
