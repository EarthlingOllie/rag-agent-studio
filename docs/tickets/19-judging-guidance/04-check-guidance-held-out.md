# 04: Check guidance on held-out reviews

**Ticket:** `19-04` · **Spec:** [Judging guidance](../../specs/19-judging-guidance-spec.md)

**What to build:** An Owner checks any guidance text before saving it: the Evaluation Model re-judges a held-out half of the Review sample reviews with it and the card shows "would agree on x of y (now z)".

**Blocked by:**
- [18-01: Prefactor: rebuild a judgement's input from what was stored](../18-verdict-review/01-prefactor-judge-input.md)
- [19-03: Agreement and Review sample per Judging setup](./03-agreement-per-judging-setup.md)

**Status:** ready-for-agent

- [ ] A guidance job (kind `check`): status, the text checked, the held-out split (a seeded random half of the current Judging setup's sample reviews, stored so a re-check uses the same halves), result, Cost, who asked, timestamps; at most one draft or check in progress per Organisation, under a lock
- [ ] The check re-judges each held-out review's target through 18-01's rebuilt input with the candidate guidance and counts agreed, false passes and false fails, beside the current Judging setup's agreement on the same reviews; Purged targets are left out; Low sample under 30
- [ ] A check never creates or changes a Verdict or Live Verdict
- [ ] Owners start and cancel a check and read its progress; Cost is frozen with the existing cost function and counted in Organisation cost's Evaluation column, never against the Evaluation budget or the Token Budget
- [ ] The guidance card shows the result; editing the text marks it out of date; the save dialog warns when agreement would drop and still saves
- [ ] The saved version keeps its latest check result
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
