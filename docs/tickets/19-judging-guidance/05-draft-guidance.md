# 05: Draft guidance from disagreements

**Ticket:** `19-05` · **Spec:** [Judging guidance](../../specs/19-judging-guidance-spec.md)

**What to build:** An Owner asks the Evaluation Model to draft guidance from Editors' disagreements, reads its explanation, edits it, checks it and saves it.

**Blocked by:**
- [19-04: Check guidance on held-out reviews](./04-check-guidance-held-out.md)

**Status:** done

- [x] Drafting is offered once the current Judging setup has at least 10 disagreeing reviews and 30 Review sample reviews; otherwise the Draft button says what is missing
- [x] The Draft dialog shows an estimated Cost (the Evaluation Model's prices for a fixed allowance per review read)
- [x] A guidance job (kind `draft`) gives the Evaluation Model the disagreeing reviews from outside the held-out half (the check, its outcome and reason, the Editor's outcome and reason, and the judged input as spotlighted data) and the current guidance; Purged Live Verdicts give outcomes only
- [x] The prompt says reviews are data, never instructions, and to write general rules without quoting replies (prompt contract test); a review trying to steer the draft is only data
- [x] Output is validated: text within 2,000 characters and an explanation linking parts to the reviews they answer; a model error, timeout or invalid output fails the job
- [x] The draft opens in the editor with its explanation; the Owner edits, checks (19-04) and saves it as a `drafted` version
- [x] Cancel, one job at a time and Cost as in 19-04
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
