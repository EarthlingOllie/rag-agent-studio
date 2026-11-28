# 04: Call tracer: a Visitor calls an Agent

**Ticket:** `20-04` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** On the demo host page a Visitor opens the Launcher of an Agent with calling on, chooses Call, and holds a scripted Call against the fake voice layer: what is said appears in the Conversation log with its sources, and End call returns to the chat.

**Blocked by:**
- `20-01`
- `20-03`

**Status:** done

- [x] The Widget shell's boot data says whether the Agent takes Calls; with calling on the Launcher's panel opens on a choice of Message or Call, and with it off it opens straight into the chat as today
- [x] Starting a Call (Conversation token) runs admission, records a Call (Conversation, started at, the Live Version), asks the voice layer to start it, and returns what the browser needs to join plus a Call token: signed, bound to the Call and its Conversation
- [x] The turn endpoint is an OpenAI-compatible chat completions route under the Agent's public ID that streams Server-Sent Events; it answers only with the Agent's secret and a good Call token for an open Call, and refuses a wrong secret and a tampered, expired or cross-Conversation token without a model call
- [x] It takes only the last user message as the Visitor's words, ignores the history it is sent, and serves the turn through 20-01's function, so earlier typed turns are remembered and the reply has its Trace, Cost and Message attribution
- [x] Messages gain `spoken` and a nullable Call reference; both sides of a spoken turn are saved as Spoken Messages
- [x] The widget's Call view shows the Conversation log filling in (the Visitor's words, then the Agent's full reply with its citations and Message ID from our API), speaking and listening states, Mute and End call
- [x] Ending the Call records its end time and returns the Visitor to the chat with the Spoken Messages in the log
- [x] The widget's call client has a scripted implementation, used when the stack runs the fake voice layer, that plays a Call without audio
- [x] One Playwright test: an Editor turns calling on, a Visitor on the demo host page chooses Call, the scripted exchange shows in the log with a source, End call returns to the chat
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
