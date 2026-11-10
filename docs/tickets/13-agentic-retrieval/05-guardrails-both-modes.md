# 05: Guardrails in Agentic mode

**Ticket:** `13-05` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Prompt-injection defences hold in Agentic mode, and the Attack evaluation suite proves it for both Retrieval Modes.

**Blocked by:**
- [13-02: Search limit, Fallback Text and turn-wide Chunk labels](02-search-limit-fallback-labels.md)

**Status:** ready-for-agent

- [ ] Each search query is checked for the Canary token before it runs; a match ends the reply as a canary leak (Fallback Text and a Guardrail outcome) and the query isn't run
- [ ] Chunks returned by Knowledge Search are spotlighted and handled by Flagged Chunk mode exactly as in Automatic mode
- [ ] The Attack evaluation suite runs each attack in both Retrieval Modes; the report gives a Pass rate per mode and CI gates both
- [ ] Specs 04 and 08 describe Agents as having no tools that act outside the Conversation, with Knowledge Search the only, read-only tool (ADR-0015)
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
