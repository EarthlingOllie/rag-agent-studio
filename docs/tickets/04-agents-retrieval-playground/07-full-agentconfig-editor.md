# 07: Full AgentConfig editor

**Ticket:** `04-07` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** Editors configure every part of an Agent: model override, temperature, max tokens, remembered turns, fallback text, retrieval settings, display name, avatar, greeting, starter questions, UI text, rating timing and Guardrail settings. The Draft is validated and saved automatically.

**Blocked by:**
- [04-01: Agent and Playground tracer](01-agent-playground-tracer.md)

**Status:** in-progress

- [ ] All configuration groups (behaviour, retrieval, experience, guardrails) are editable; guardrail settings are stored only, until spec 08
- [ ] Validation against the capability registry gives clear messages
- [ ] Drafts autosave, with an indicator
- [ ] Credential references are registered for the model override, reranker and classifier
- [ ] The AgentConfig JSON Schema is exposed through OpenAPI and covered by the client drift check
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
