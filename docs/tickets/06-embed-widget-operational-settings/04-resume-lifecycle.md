# 04: Resume and Conversation lifecycle

**Ticket:** `06-04` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** A Visitor who reloads within 24 hours gets their Conversation back, can start a new one or end it, and sees a friendly message when an Agent has been retired.

**Blocked by:**
- [06-01: Embed tracer](01-embed-tracer.md)

**Status:** in-progress

- [ ] The Conversation token is kept in iframe storage, and resume works within a 24-hour sliding window and is refused after it
- [ ] Visitors can start a new Conversation or end the current one
- [ ] Archived or never-published Agents render the "no longer available" shell
- [ ] The widget degrades gracefully when storage is unavailable
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
