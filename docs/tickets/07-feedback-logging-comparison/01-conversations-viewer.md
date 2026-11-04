# 01: Conversations viewer

**Ticket:** `07-01` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Editors browse Conversations per Agent and per Project, filter them, and open one to read it with each reply's Trace inline.

**Blocked by:**
- [06-01: Embed tracer](../06-embed-widget-operational-settings/01-embed-tracer.md)
- [04-06: Citations and Trace drawer](../04-agents-retrieval-playground/06-citations-trace.md)

**Status:** ready-for-agent

- [ ] The list can be filtered by date, Version and Playground
- [ ] The detail view shows Messages with a Trace drawer
- [ ] Playground Conversations are clearly flagged
- [ ] Tenant isolation tests are extended
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
