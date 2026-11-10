# 03: Widget searching status

**Ticket:** `13-03` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Visitors of an embedded Agentic Agent see a short, accessible "Searching the knowledge base…" status while it searches, which Editors can reword.

**Blocked by:**
- [13-01: Agentic tracer](01-agentic-tracer.md)

**Status:** ready-for-agent

- [ ] The widget SSE stream gains a `search` event that carries no query
- [ ] The widget shows a searching status row while Searches run, replaced when the answer starts streaming
- [ ] The status is announced once per reply through the existing polite live region
- [ ] UI text overrides gain `searching_status`; the widget uses it when set
- [ ] The Token Budget counter is incremented with the reply's summed tokens; the Playground stays exempt
- [ ] Purging Message text (Retention Window) also purges search queries
- [ ] The axe checks cover the widget with the status showing
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
