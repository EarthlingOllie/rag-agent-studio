# 02: Message Feedback

**Ticket:** `07-02` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Visitors give a thumbs up or down, with an optional comment, on any Agent reply, and can change or remove it. Editors see the feedback in the Conversation viewer.

**Blocked by:**
- [07-01: Conversations viewer](01-conversations-viewer.md)

**Status:** done

- [x] The widget offers thumbs plus an optional comment, which can be changed or removed
- [x] Feedback is only allowed on Messages in the Visitor's own Conversation
- [x] Feedback is attributed to the Message's Version, stored when written
- [x] The viewer shows feedback and can filter by it
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
