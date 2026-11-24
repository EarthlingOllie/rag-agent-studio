# 03: Agreement and Review sample per Judging setup

**Ticket:** `19-03` · **Spec:** [Judging guidance](../../specs/19-judging-guidance-spec.md)

**What to build:** Evaluation Model agreement and the Review sample work per Judging setup, so an Owner sees whether new guidance changed how often Editors agree.

**Blocked by:**
- [19-01: Judging guidance tracer: save it, judge with it, record the Judging setup](./01-judging-guidance-tracer.md)
- [18-03: Live Verdict checks in the Review sample, and retention](../18-verdict-review/03-live-verdicts-in-sample-retention.md)
- [18-05: Evaluation Model agreement card](../18-verdict-review/05-agreement-card.md)

**Status:** done

- [x] Verdict reviews record the Judging setup of the judgement they review
- [x] The Review sample pool holds only judgements under the current Judging setup
- [x] The agreement card shows the current Judging setup's figures and lists earlier Judging setups (Evaluation Model and guidance version) that have reviews
- [x] Changing either the Evaluation Model or the guidance starts new figures
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
