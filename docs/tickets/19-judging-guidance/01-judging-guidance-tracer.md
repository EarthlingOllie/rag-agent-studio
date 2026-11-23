# 01: Judging guidance tracer: save it, judge with it, record the Judging setup

**Ticket:** `19-01` · **Spec:** [Judging guidance](../../specs/19-judging-guidance-spec.md)

**What to build:** An Owner writes and saves Judging guidance in Organisation settings › Models; new Evaluation Runs and Live Verdicts are judged with it and record their Judging setup, shown in the Run header.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] A Judging guidance version: Organisation, version number, text (up to 2,000 characters; empty means none), source (`written` or `drafted`), saved_by, saved_at; the Organisation points at its current version
- [ ] Saving creates a new version, makes it current and records an `organisation.judging_guidance_changed` Audit Event with before and after; removing saves an empty version; Owners only
- [ ] The judge adds the current guidance as an "Organisation guidance" section after its fixed instructions and outside the spotlighted data blocks; spec 14's contract test is extended to show it
- [ ] Evaluation Runs and Live Verdicts record the guidance version beside the Evaluation Model they already copy (their Judging setup); earlier ones keep theirs
- [ ] The fake judge and the Demo model's judging path gain one rule: with a scripted phrase in the guidance, "answers the question" passes partial answers that say what they don't cover
- [ ] Organisation settings › Models gains a Judging guidance card: current text and version, version history, Edit for Owners, read-only for Editors
- [ ] Run detail shows the Run's Judging setup in its header
- [ ] Another Organisation's guidance is unreachable
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
