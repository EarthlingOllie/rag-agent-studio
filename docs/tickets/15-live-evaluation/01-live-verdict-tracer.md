# 01: Live Verdict tracer: sample a reply and judge it

**Ticket:** `15-01` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** An Editor sets an Agent's Live sample rate in Embed & limits; a Visitor reply in the widget is sampled and judged in the background by the Evaluation Model, and its Live Verdict (grounded, answers the question, with reasons) shows in the reply's Trace.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] Operational Settings gain `live_sample_rate` (whole percentage, 0 to 100, default 0), readable and settable by Editors and Owners through the API; changes are recorded as `agent.live_sample_rate_changed` Audit Events with before and after
- [ ] Live Verdict is stored, one per sampled Agent Message, with status (`pending`, `judged`, `error`, `skipped`), the `grounded` and `answers_question` outcomes and reasons, the overall pass, the Evaluation Model used, Cost and token usage, and the Agent and Agent Version copied from the Message
- [ ] After a Visitor reply is stored, it is a candidate unless it was a Guardrail block or the Fallback Text; a random draw under the Agent's rate chooses it; a chosen reply gets a `pending` Live Verdict and a Celery task after commit; the draw uses one random source that test settings can seed
- [ ] Playground replies are never sampled, and sampling or judging never delays or changes the Visitor's reply
- [ ] The task judges the question, the reply and the Chunks it was given (with cited flags) through the Model gateway with the Evaluation Model, using spec 14's judge extended with an `answers_question` check; both checks come from one structured-output call at temperature 0; the reply passes when both pass
- [ ] The judge's Cost is frozen with the existing cost function and Price table and stored on the Live Verdict
- [ ] The fake judge and the Demo model's judging path gain `answers_question` by rule (passes when the reply shares a scripted key phrase with the question)
- [ ] The Trace payload gains the Live Verdict, and the Studio Trace shows a Live Verdict section: both outcomes with reasons, pending, or "Not judged"
- [ ] Embed & limits gains the Live sample rate field, explaining that replies are judged by the Evaluation Model
- [ ] Every Member can read Live Verdicts; another Organisation's are unreachable; an archived Agent's replies are never sampled
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
