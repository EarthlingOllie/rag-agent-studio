# 03: Evaluation budget

**Ticket:** `15-03` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** An Owner sets a monthly Evaluation budget in US dollars; without one, no Agent can be sampled; when the month's spend reaches it, sampling pauses across the Organisation and Owners are emailed once; a meter shows spend against it.

**Blocked by:**
- [15-01: Live Verdict tracer: sample a reply and judge it](01-live-verdict-tracer.md)

**Status:** done

- [x] Organisation settings gain the Evaluation budget (nullable US dollars), get and set by Owners only, recorded as `organisation.evaluation_budget_changed` Audit Events with before and after
- [x] Setting a Live sample rate above 0% is refused with a typed error while the Organisation has no budget; removing the budget keeps rates but stops all sampling
- [x] A monthly spend record per Organisation and calendar month (UTC) accumulates each Live Verdict's Cost with an atomic update
- [x] No reply is sampled once the month's spend has reached the budget; judgements already pending finish; Visitor replies are unaffected
- [x] The judgement that takes spend to or past the budget emails every Owner once for that month
- [x] Raising the budget resumes sampling at the next reply; a new month starts a new record, so sampling resumes on the 1st with no job
- [x] Live Verdict Cost counts in Organisation cost's Evaluation column on the day of the judgement, and never in the Token Budget or Version KPIs' cost
- [x] Evaluation Runs that Editors start are never capped by the budget
- [x] Organisation settings (Models) show the budget field and this month's meter beside the Evaluation Model and Evaluation repeats (read-only for Editors); the Cost page shows the meter above its table
- [x] The Live sample rate field is disabled with a link to Organisation settings while there is no budget
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
