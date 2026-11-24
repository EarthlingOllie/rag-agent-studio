# 08: Voice Cost

**Ticket:** `20-08` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** An Owner sees what the voice layer costs: each Call's minutes and Voice Cost on its Conversation, and rolled into Agent, Project and Organisation cost.

**Blocked by:**
- `20-07`

**Status:** ready-for-agent

- [ ] The Price table gains a per-minute price for ElevenLabs voice, dated like the rest, and a credential's Price overrides can replace it
- [ ] Ending a Call freezes its Voice Cost: its minutes times the price in effect then, preferring the override; unknown when no price is set
- [ ] The Conversations viewer shows each Call's minutes and Voice Cost, apart from the Cost of its replies
- [ ] Daily rollups add Voice Cost per Agent Version; the Agent, Project and Organisation cost views show it as its own line and in their totals
- [ ] Credentials lets an Owner override the per-minute price for an ElevenLabs credential
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
