# 01: Prefactor: rebuild a judgement's input from what was stored

**Ticket:** `18-01` · **Spec:** [Verdict review](../../specs/18-verdict-review-spec.md)

**What to build:** What the Evaluation Model was given for any judged Run Verdict or Live Verdict can be rebuilt from stored data, through one function both Run judging and Live judging use; nothing visible changes.

**Blocked by:**
- None

**Status:** done

- [x] One function in the `evaluation` module returns the judge request for a stored target: a judged Evaluation Verdict (from the Run's copied case, the case result's stored answer and Trace) or a Live Verdict (from its Message, Remembered turns and traced Chunks, as Live judging builds it today)
- [x] It returns nothing when the target's text has been Purged, so nothing is shown or re-judged without its text
- [x] Run judging and Live judging build their requests through it; spec 14's and spec 15's judge contract tests pass unchanged
- [x] A test shows the rebuilt request for a stored Run result equals the one the Run judged with, and likewise for a Live Verdict
- [x] No behaviour or API change
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
