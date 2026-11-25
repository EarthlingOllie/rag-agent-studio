# 05: Real ElevenLabs adapter

**Ticket:** `20-05` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** With a real ElevenLabs credential and a public base URL, a Visitor holds a real Call: the browser joins ElevenLabs over WebRTC and hears the Agent's replies.

**Blocked by:**
- `20-04`

**Status:** ready-for-agent

- [ ] The voice layer's production adapter creates, updates and removes the remote agent, lists voices and mints a WebRTC token with the Organisation's credential; it is tested against recorded HTTP exchanges
- [ ] The widget joins with the ElevenLabs browser client, loaded only when a Visitor picks Call, and passes the Call token as the extra body; Visitors who never call download none of it
- [ ] The Widget shell's CSP allows connections to ElevenLabs only for an Agent with calling on
- [ ] The Embed Snippet's loader gives the iframe microphone permission and stays inside its size budget
- [ ] Widget tests replace the ElevenLabs client with a fake at the module boundary: transcripts reach the log, speaking and listening states show, Mute mutes
- [ ] A test in the live suite sets up a remote agent on a real account, mints a token and removes the agent
- [ ] docs/development.md explains holding a real Call locally through a tunnel
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
