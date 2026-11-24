# 10: Moving between typing and talking

**Ticket:** `20-10` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** A Visitor moves between typing and talking inside one Conversation, and gets their Call back with one tap after a reload.

**Blocked by:**
- `20-04`

**Status:** ready-for-agent

- [ ] The chat header has a Call button for an Agent with calling on; End call returns to the chat with everything said in the log
- [ ] The text box is hidden during a Call
- [ ] The spoken greeting is heard only when a Call opens a Conversation with no Messages, and is not saved as a Message; any other Call opens with the Agent listening
- [ ] A reload or page change ends the Call; the resumed Conversation shows its Spoken Messages and offers "Continue call", which starts a new Call on one tap and never opens the microphone by itself
- [ ] A Conversation can hold several Calls; the Agent remembers typed and spoken turns alike in each
- [ ] New chat and End chat end any open Call
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
