# 05: Expected sources and Expect Fallback Text

**Ticket:** `14-05` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** In the case editor, an Editor picks passages from a Document as Expected sources or marks a case Expect Fallback Text; Runs check whether the answer cited the passage or gave the Fallback Text, and an Expected source whose passage no longer exists is a Stale expectation, skipped and flagged.

**Blocked by:**
- [14-02: Evaluation tracer: one case, the Draft alone, one judged answer](02-evaluation-tracer.md)

**Status:** ready-for-agent

- [ ] A case can hold several Expected sources, each a Document and a passage of up to 1,000 characters, chosen in a picker that opens the Document's current Chunks
- [ ] Expect Fallback Text can't be combined with an Expected source or a Reference answer; the refusal names the field
- [ ] The `expected_source` Verdict passes when a current-Edition Chunk containing the passage (case and whitespace normalised) was cited, fails when it wasn't (retrieved but uncited is a fail, and the reason says so), and is `stale` when the Document is gone or no Chunk contains the passage
- [ ] The `fallback` Verdict passes when the answer was the Fallback Text (or the Refusal text) and fails otherwise
- [ ] Stale Verdicts count as neither pass nor fail; a case with a Stale expectation is flagged in the Evaluation Set and in Run detail
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
