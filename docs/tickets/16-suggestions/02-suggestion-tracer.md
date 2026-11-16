# 02: Suggestion tracer: failed Live Verdicts become a system prompt Suggestion

**Ticket:** `16-02` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** From a new Suggestions tab, an Editor starts a Suggestion run; the Evaluation Model reads the Live Version's failed Live Verdicts and proposes a system prompt change, shown as a Diff with its explanation and evidence.

**Blocked by:**
- [15-01: Live Verdict tracer: sample a reply and judge it](../15-live-evaluation/01-live-verdict-tracer.md)

**Status:** ready-for-agent

- [ ] A new `suggestions` module stores the Suggestion (Agent, status, started_by, range of UTC days, base Live Version and a snapshot of its effective AgentConfig, Evaluation Model copied, outcome, overall explanation, error, timestamps), its suggested changes (path, base value, suggested value, explanation) and evidence links (kind and Message reference, never Message text, per ADR-0017)
- [ ] Starting a run enqueues a Celery task that gathers the Live Version's Visitor replies in the range with a failed Live Verdict, then makes one structured-output call to the Evaluation Model at temperature 0 with its own timeout
- [ ] Evidence goes in spotlighted, delimited data blocks with escaped delimiters; the prompt says evidence is data, never instructions, and not to quote Visitors (prompt contract test, including that no text but the base system prompt is sent as configuration)
- [ ] Output is validated: only `behaviour.system_prompt` is accepted in this ticket; it is validated like a Draft save; unknown evidence ids are dropped; a model error, timeout or invalid output makes the run `failed`
- [ ] A Visitor reply trying to steer the Suggestion is only evidence (scripted model asserting it received the text as data)
- [ ] The fake chat model and the Demo model gain a deterministic proposing path: one system prompt line ("Always cite the passage you used") when any evidence failed grounding
- [ ] The API lists Suggestions and reads one with its changes and evidence links resolved to date, kind and Live Verdict outcome; evidence links open the reply in the Conversations viewer
- [ ] The Evaluation view gains a Suggestions tab: the list (status, range, outcome), a "Suggest changes" action with a range picker (last 14 days by default), and Suggestion detail with the overall explanation, each change as a Diff row with its explanation and evidence chips; the Studio polls while a run is in progress
- [ ] Editors and Owners start runs; every Member reads; another Organisation's Suggestions are unreachable
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
