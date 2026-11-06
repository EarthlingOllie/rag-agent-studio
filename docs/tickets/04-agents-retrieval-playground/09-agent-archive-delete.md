# 09: Agent Archive and delete

**Ticket:** `04-09` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** Editors archive Agents they no longer need without losing history. Owners can restore them, or permanently delete them after typing the name.

**Blocked by:**
- [04-01: Agent and Playground tracer](01-agent-playground-tracer.md)

**Status:** in-progress

- [ ] Archive and restore work, and archived Agents are excluded from lists and the Playground
- [ ] Owners can permanently delete after typing the name, which cascades
- [ ] Everything is recorded as Audit Events
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
