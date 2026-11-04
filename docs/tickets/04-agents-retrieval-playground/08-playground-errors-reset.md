# 08: Playground errors and reset

**Ticket:** `04-08` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** When the provider fails, the Playground explains why (invalid key, rate limited, model unavailable). Editors can reset the Playground to a fresh Conversation.

**Blocked by:**
- [04-01: Agent and Playground tracer](01-agent-playground-tracer.md)

**Status:** ready-for-agent

- [ ] Provider errors become typed error events with readable messages
- [ ] Reset starts a new Playground Conversation
- [ ] Truncation to the configured number of remembered turns is verified
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
