# 03: Live Verdict checks in the Review sample, and retention

**Ticket:** `18-03` · **Spec:** [Verdict review](../../specs/18-verdict-review-spec.md)

**What to build:** Both checks of a Live Verdict (grounded, answers the question) can be reviewed blind in the Review sample, with the reply's Remembered turns shown; the Purge clears reasons on those reviews and keeps their outcomes.

**Blocked by:**
- [18-02: Verdict review tracer: blind Review sample of Run Verdicts](./02-verdict-review-tracer.md)

**Status:** done

- [x] A Verdict review can target a Live Verdict plus its check (`grounded`, `answers_question`), unique per pair
- [x] The pool adds both checks of every judged Live Verdict by the current Evaluation Model that isn't purged and has no review; Error and skipped Live Verdicts are never in it
- [x] The Review sample shows a Live check's Remembered turns, question, reply and given Chunks with cited flags, then reveals that check's outcome and reason
- [x] The Purge pass that clears a Live Verdict's reasons clears the reason on its reviews and stamps them purged-at; their outcomes stay and agreement is unchanged
- [x] Deleting a Conversation does the same at once
- [x] A purged Live Verdict leaves the pool
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
