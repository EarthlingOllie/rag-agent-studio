# 10: Agentic answers stream word by word

**Ticket:** `13-10` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** An Agentic Agent's reply streams word by word, exactly like an Automatic one, in the Playground and the widget. If a model response that has already streamed text turns out to call Knowledge Search, that text is retracted: clients clear it, show the Search, and then stream the answer that follows. This supersedes 13-02's choice to hold each Agentic response's text until the response ends (a product owner decision).

**Blocked by:**
- [13-04: Search limit and Fallback Text](04-search-limit-fallback.md)
- [13-06: Widget searching status and Token Budget](06-widget-searching-status.md)
- [13-07: Guardrails in both modes](07-guardrails-both-modes.md)

**Status:** done

- [x] In Agentic mode the runtime streams each model response's text as it arrives; nothing holds it until the response ends
- [x] When a response that already streamed text calls Knowledge Search, the runtime emits a `RetractEvent`, sent as an SSE `retract` event with no data to the Playground, the widget and the Attack panel, before that Search's `search` event; it records no Guardrail outcome
- [x] Retracted text never becomes part of the saved reply, the Trace, the `done` payload or the Citations (a Chunk label written only in retracted text is not cited)
- [x] Every streamed piece of every response goes through the reply's Canary filter: a canary that starts to appear in any response, retracted or not (also straddling chunks), stops the stream and replaces the reply with a `replace` event and the same Guardrail outcome as in Automatic mode; the filter's held-back text is dropped on a retraction, never released; a disguised canary in retracted text is flagged like one in the answer; the search-query canary check is unchanged
- [x] When the reply searched and no Search reached the Minimum Score, the Fallback Text is decided as the next response starts: it is sent with no answer tokens streamed first, and if that response searches again it is retracted like any other text
- [x] The Playground clears the retracted answer text, keeps its "Searching: …" lines and streams the answer that follows
- [x] The widget clears the retracted text and shows its searching status row; the status is announced once per reply through the polite live region, and retracted text is never announced; the widget never shows the model's query
- [x] The `retract` event is documented in the OpenAPI descriptions of the Playground and widget streams and in the module docstrings; `make check-client` passes
- [x] The spec's runtime section and Further Notes, the runtime module docstring and ADR-0015 say Agentic answers stream with retraction; 13-02's evidence notes that 13-10 supersedes its hold
- [x] The end-to-end specs for the Playground, the widget and the Attack panel cover the change and lint, typecheck and list
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
