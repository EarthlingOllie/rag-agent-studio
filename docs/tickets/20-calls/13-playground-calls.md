# 13: Playground Calls

**Ticket:** `20-13` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** An Editor calls the Draft from the Playground and hears it answer, with each spoken reply opening its Trace.

**Blocked by:**
- `20-06`

**Status:** ready-for-agent

- [ ] The Playground has a Call button when the Agent's calling is on, and says how to turn it on when it is off
- [ ] A Playground Call speaks with the Agent's Call settings and answers with the Draft and the picked Project Instructions
- [ ] Its turns go through the same turn endpoint with a Playground Call token, and are saved as Spoken Messages of the Playground Conversation, each with its Trace
- [ ] Searches show their queries in the Playground as they do for typed questions
- [ ] Playground Calls stay out of metrics, the Token Budget and the Call minutes budget; their Voice Cost and model Cost count in Organisation cost
- [ ] Reset ends an open Call
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
