# 06: Widget searching status and Token Budget

**Ticket:** `13-06` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Visitors of an embedded Agentic Agent see a short, accessible "Searching the knowledge base…" status while it searches, which Editors can reword, and the Token Budget counts everything the reply used.

**Blocked by:**
- [13-02: Agentic tracer: one Knowledge Search, end to end](02-agentic-tracer.md)

**Status:** done

- [x] The widget SSE stream gains a `search` event that carries no query
- [x] The widget shows a searching status row while Searches run, replaced when the answer starts streaming
- [x] The status is announced once per reply through the existing polite live region
- [x] UI text overrides gain `searching_status`; the widget uses it when set
- [x] The Token Budget counter is incremented with the reply's summed tokens; the Playground stays exempt
- [x] The axe checks cover the widget with the status showing
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
