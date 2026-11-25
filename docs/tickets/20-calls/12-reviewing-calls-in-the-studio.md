# 12: Reviewing Calls in the Studio

**Ticket:** `20-12` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** An Editor reviews and measures Calls: Spoken Messages marked in the Conversations viewer, a filter for Conversations with a Call, Calls and Call minutes in Analytics, and the Launcher's two choices reworded per Agent.

**Blocked by:**
- `20-07`

**Status:** ready-for-agent

- [ ] The Conversations viewer marks Spoken Messages and interrupted replies, and shows a row for each Call with when it started and its minutes
- [ ] A "Has a Call" filter narrows the Conversations list, in the Project section and in the Agent view
- [ ] Daily rollups add Calls and Call minutes per Agent Version; Analytics shows both per day
- [ ] Spoken replies count in the existing Version KPIs, Live sampling and Evaluation with no special case; a test shows a spoken reply in each
- [ ] The Purge clears Spoken Messages' text like typed ones and keeps Calls, minutes and Voice Cost
- [ ] UI text overrides gain `message_choice` and `call_choice`; they are in the Draft, Versions and Diffs, and the widget shows them on the choice screen
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
