# 04: Suggestion run dialog, Cost and lifecycle

**Ticket:** `16-04` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** Before starting, an Editor sees how much evidence the range holds, a warning when it's thin, and the estimated Cost; runs can be cancelled, never overlap with Evaluation Runs, and their Cost is counted.

**Blocked by:**
- [16-02: Suggestion tracer: failed Live Verdicts become a system prompt Suggestion](02-suggestion-tracer.md)

**Status:** ready-for-agent

- [ ] An evidence-count read returns the counts by kind for a range, without the cap; the dialog shows them and warns below 10 that a Suggestion is likely to be noise, without blocking
- [ ] An estimate read returns proposing Cost (Evaluation Model prices for a fixed allowance per piece of evidence plus an output allowance) and, when the Agent has an Evaluation Set, checking Cost from spec 14's estimator for two sides; both are shown and stored on the Suggestion
- [ ] Actual proposing Cost is frozen as it is spent, shown on the Suggestion and counted in Organisation cost's Evaluation column; the Evaluation budget never applies
- [ ] Status moves through `queued`, `gathering`, `proposing`, `checking`, `completed`; the Studio shows the phase
- [ ] An Editor can cancel a run; it stops between phases and keeps what it spent
- [ ] At most one Suggestion run is in progress per Agent; starting one is refused while an Evaluation Run is in progress, and Evaluate is refused while a Suggestion run is in progress, each with a typed conflict, enforced together under a lock on the Agent
- [ ] Starting is refused for an Agent that has never been Published or is archived; an archived Agent's Suggestions stay readable
- [ ] Permanent deletion of an Agent removes its Suggestions
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
