# 07: Expected source warning and re-checking after a new Edition

**Ticket:** `14-07` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** Before an Editor deletes a Document, or uploads a new Edition of one, that holds an Expected source, the Studio warns which Agents and how many cases; when a new Edition is Ready its Expected sources are checked again at once.

**Blocked by:**
- [14-05: Expected sources and Expect Fallback Text](05-expected-sources-fallback.md)

**Status:** ready-for-agent

- [ ] A read on a Document returns the Agents and case counts holding an Expected source in it
- [ ] The delete confirmation and the new-Edition upload show the Expected source warning when there are any; neither is blocked
- [ ] When a Staged edition is swapped in, every Expected source on that Document is re-matched: surviving passages stay valid, missing ones become Stale expectations (`passage_missing`), and earlier Stale ones whose passage is back are cleared
- [ ] Deleting a Document marks its Expected sources Stale (`document_deleted`) and keeps the Document's name for display
- [ ] The Document viewer marks passages used as Expected sources
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
