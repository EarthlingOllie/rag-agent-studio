# 09: Agentic by default, with the demo and seed

**Ticket:** `13-09` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** New Agents start Agentic, and the Demo Organisation shows the trade-off: one Agentic and one Automatic Agent over the same Project, both working without a real Provider Credential.

**Blocked by:**
- [13-03: Models that support tools](03-tool-capable-models.md)
- [13-04: Search limit and Fallback Text](04-search-limit-fallback.md)
- [13-07: Guardrails in both modes](07-guardrails-both-modes.md)

**Status:** done

- [x] `mode` defaults to Agentic for new Agents
- [x] In Agentic mode the Demo model and the Naive demo model make one Knowledge Search with the Visitor's question, then answer from the first Chunk it returned
- [x] The seed creates one Agentic and one Automatic Agent over the same Project, each with its mode set explicitly; the Attack panel's Guardrail demo Agent is explicitly Automatic
- [x] The Five-minute demo script points out the difference between the two Agents' Traces
- [x] A live-suite test makes one real Anthropic or OpenAI Agentic reply against the seed Knowledge Base that searches and cites a Chunk
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [13-09-evidence/README.md](13-09-evidence/README.md). The live-suite test is written and skips without a provider key; it was not run live here (see the evidence's Gaps).
