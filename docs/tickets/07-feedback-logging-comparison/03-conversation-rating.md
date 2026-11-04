# 03: Conversation Rating

**Ticket:** `07-03` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Visitors are asked to rate the Conversation from 1 to 5 after a configurable number of replies, and again when they end the chat. They can dismiss the prompt or change their rating later.

**Blocked by:**
- [07-02: Message Feedback](02-message-feedback.md)

**Status:** ready-for-agent

- [ ] The prompt appears after the Nth reply (a Live Version setting) and on end if no rating has been given; a dismissal is saved
- [ ] Changing a rating is recorded in a change log
- [ ] A rating is attributed to the Version of the last Agent Message before it
- [ ] The viewer shows ratings and can filter by them
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
