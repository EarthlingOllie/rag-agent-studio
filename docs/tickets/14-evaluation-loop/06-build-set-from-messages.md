# 06: Building the set: add from a Message, copy, cap and filters

**Ticket:** `14-06` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** An Editor turns any Agent Message, in the Conversations viewer or the Playground, into an Evaluation Case with its question prefilled and the cited passages offered; copies cases from another Agent; and works with a capped, filterable set. Cases outlive the Retention Window (ADR-0016).

**Blocked by:**
- [14-05: Expected sources and Expect Fallback Text](05-expected-sources-fallback.md)

**Status:** ready-for-agent

- [ ] "Add to Evaluation Set" in each Agent Message's ⋯ menu in the Conversations viewer and the Playground opens the case editor with the preceding Visitor question (editable) and the cited passages offered as Expected sources, unticked; the editor says no link to the Conversation is kept
- [ ] Prefill is refused for a purged Message and for another Agent's Message
- [ ] Saving a case from a Message records `agent.evaluation_case_added_from_message` (case and Agent, no question text); deleting a case records `agent.evaluation_case_deleted`; writing and editing cases are not audited
- [ ] The case keeps no reference to the Conversation or Message; the Purge, run directly, clears the source Conversation and leaves the case untouched
- [ ] Cases can be copied from another Agent in the same Project as independent copies
- [ ] An Evaluation Set holds at most 200 cases, enforced under concurrent creates and copies, with a clear message at the limit
- [ ] The set list can be searched and filtered by expectation kind, Stale flag and latest result
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
