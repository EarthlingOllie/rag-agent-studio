# 09: When a Call can't start

**Ticket:** `20-09` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** A Visitor whose Call can't start is told why and lands in messaging, and the Studio shows when Calls are failing.

**Blocked by:**
- `20-04`

**Status:** ready-for-agent

- [ ] The microphone is requested only after the Visitor chooses Call
- [ ] A refused microphone, or a host page whose policy blocks it, shows a short explanation and opens the chat
- [ ] A voice layer failure when starting a Call (the remote agent is gone, the key was revoked, the provider is unreachable) gives the Visitor the Unavailable text and the chat, and raises the Agent's Calls failing alert
- [ ] A connection that drops mid-Call ends the Call, says so and returns to the chat
- [ ] The alert shows on the Agents list and on Embed & limits; saving the Call settings sets the remote agent up again and clears it, as does the next Call that starts
- [ ] Messaging is unaffected throughout
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
