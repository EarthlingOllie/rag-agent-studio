# 03: Evaluation Model, Evaluation repeats and combining results

**Ticket:** `14-03` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** Owners choose the Evaluation Model and the Evaluation repeats in Organisation settings; Runs answer each case that many times, a case passes by majority, Unsteady cases are marked, and cases that couldn't be answered or judged are Errors, left out of the Evaluation score.

**Blocked by:**
- [14-02: Evaluation tracer: one case, the Draft alone, one judged answer](02-evaluation-tracer.md)

**Status:** ready-for-agent

- [ ] Organisation settings (Models) let Owners choose an Evaluation Model (a chat-capable Provider Credential and model, or "Use the Default Model"); it is a Credential reference, so its credential can't be deleted while chosen; Editors can't change it
- [ ] Owners set Evaluation repeats to 1, 3, 5, 7 or 9 (default 3); other values are refused
- [ ] Changing either is an Audit Event (`organisation.evaluation_model_changed`, `organisation.evaluation_repeats_changed`) with before and after values
- [ ] A Run copies the Evaluation Model and repeats in force when it starts and shows them; later changes don't alter it
- [ ] Each repeat is a fresh answer judged once; a repeat passes when every Verdict that isn't Stale passes; a case passes on a side when most of its answered repeats do, and shows its count (for example 2/3)
- [ ] A case whose repeats disagree is marked Unsteady
- [ ] Provider and judge errors and timeouts make a case result an Error with its reason; a case whose every repeat errored is an Error on that side and is left out of the Evaluation score
- [ ] A Guardrail block on a case is an answer and is judged (normally a fail), not an Error
- [ ] A Run where every case errored ends `failed` with the most common error as its message
- [ ] The Evaluation Set list shows each case's latest result: pass, fail, Unsteady or Error
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
