# Evidence: ticket 13-03, Models that support tools

Branch `t/13-03`, from `0823a537` (the integration branch: all of spec 12, plus merged `t/13-01` and `t/13-02`). The change is one commit; every check below ran on its tree, and only this folder was written afterwards.

**Status: done.** Every criterion is met and evidenced below. The Playwright run is deferred to the integrated branch (see [End-to-end](#end-to-end-deferred)).

## What was built

- **Capability registry** (`backend/app/credentials/registry.py`): each `Model` has `supports_tools` (false by default: embedding and rerank models call no tools). Chat models are declared with `chat(...)`, which supports tools unless told otherwise. Every chat model supports tools, the Demo model and the Naive demo model included, except one added for it: **Bedrock's Mistral 7B Instruct** (`mistral.mistral-7b-instruct-v0:2`), which Bedrock's Converse API gives no tool use. It is priced in `price_table.json` ($0.15 input, $0.20 output per million tokens, from 2024-03-01), as the price-table test requires of every registry model. `supports_tools(provider, model)` answers false for a model the registry doesn't list. The fake chat model stands in for the registry's provider models, so it is used with whatever flag the model has; it already makes the scripted Knowledge Search when offered the tool (13-02).
- **Listings**: `ModelOut` (in `GET /api/providers` and `GET …/credentials/{id}/models/{capability}`) and `DefaultModelOut` (`GET`/`PUT …/default-model`) carry `supports_tools`. The JSON Schema and the generated client are regenerated.
- **Draft validation** (`backend/app/agents/validation.py`): saving a Draft in Agentic mode checks the effective chat model. With a Model override that lacks tool support the problem is at `behaviour.model.model`; with none, the Default Model's is at `retrieval.mode`. The message names the model and the way out ("Agentic Retrieval Mode needs a model that supports tools, and the Default Model (Mistral 7B Instruct) doesn't. Choose Automatic, or a model that supports tools."), type `model_without_tools`. An override already refused (not offered, unknown credential) is reported once, as before; with no model at all nothing is checked (the Playground says what is missing). Reverting the Live Version is unchanged: it isn't a Draft save, and the runtime fallback covers it.
- **Automatic fallback at reply time** (`backend/app/playground/service.py`, `save_question`, shared by the Playground and the widget): when an Agentic configuration's effective model lacks tool support (the Default Model changed after the Draft was saved; that change revalidates nothing), the reply runs with the configuration's Retrieval Mode set to Automatic, and the answer Message stores `automatic_fallback` (migration `0041_automatic_fallback`). The Trace (`TraceOut`, Playground and Conversations viewer) returns `automatic_fallback`. `run_turn` is unchanged.
- **Studio** (design-system tokens and the shared `Notice` only):
  - `settings/ModelOptions.tsx`: a chat model picker's options grouped in `<optgroup>`s "Supports tools: Agentic or Automatic" and "No tools: Automatic only" (option names are unchanged, so existing selectors keep working).
  - `projects/DraftEditor.tsx`: the **Model override** picker (only; the reranker and LLM classifier don't call tools) uses the groups and, for a chosen model without tools, says "… can't use tools, so this Agent can only use Automatic Retrieval Mode." A refusal at `behaviour.model.model` shows on the picker as before. The change is confined to the model picker (13-05 owns the Retrieval section).
  - `settings/ModelsPage.tsx`: the Default Model picker uses the groups and warns for a chosen model without tools; the current Default Model says when it can't use tools.
  - `projects/Trace.tsx`: a warning `Notice` when `automatic_fallback` is set: "This Agent is Agentic, but its model can't use tools, so it answered as Automatic: …"; the Chunks of the one search up front are listed as in Automatic mode.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams); spec 13 adds none. No human was available to confirm seams, so these are the pre-agreed ones.

- **API seam** (`backend/tests/integration/test_tool_capable_models.py`, real Postgres and Redis, scripted `FunctionModel`, fake credential verifier):
  - `test_the_registry_says_which_models_support_tools`: every chat model but Mistral 7B Instruct supports tools, the Demo models included; no embedding or rerank model does.
  - `test_a_credentials_chat_models_say_whether_they_support_tools` (a Bedrock access-keys credential) and `test_the_default_model_says_whether_it_supports_tools`.
  - `test_an_agentic_draft_is_refused_when_the_default_model_cant_use_tools`: 422 at `retrieval.mode` with the reason; the Draft stays Automatic; an Automatic save still works.
  - `test_an_agentic_draft_is_refused_when_its_model_override_cant_use_tools`: 422 at `behaviour.model.model`; an override with tools saves even when the Default Model lacks them.
  - `test_an_override_the_credential_doesnt_offer_is_refused_once` and `test_an_agentic_draft_without_any_model_is_not_refused_for_tools`.
  - `test_an_agentic_agent_answers_as_automatic_when_the_default_model_cant_use_tools`: the model is offered no tool, the stream has no `search`, the answer cites the Chunk found up front, the Trace has `automatic_fallback` true, no Searches and the Automatic `chunks`; the Draft is still Agentic.
  - `test_an_agentic_reply_on_a_model_with_tools_has_no_fallback_warning`.
  - `test_a_visitor_of_an_agentic_live_version_is_answered_as_automatic_after_the_change`: the widget answers, and the Studio's Conversations Trace carries the warning.
  - Existing listing tests extended with the new field (`test_default_model.py`, `test_provider_credentials.py`, `tests/unit/test_model_gateway.py`).
- **Frontend network seam (MSW)**:
  - `ModelsPage.test.tsx`: the picker groups models by tool support and warns for one without; the current Default Model without tools says Agentic Agents answer as Automatic.
  - `DraftEditor.test.tsx`: the Model override picker groups a Bedrock credential's models, warns for Mistral 7B Instruct and saves it; the LLM classifier's picker isn't grouped.
  - `AgentPage.test.tsx`: the Trace drawer shows the Automatic-fallback warning with the Retrieved Chunks table, and none for an Agentic answer that searched.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | `supports_tools` on each registry Model, in credential and model listings; Demo models and the fake chat model support tools | `registry.py`, `ModelOut`, `DefaultModelOut`; the three listing tests above; `test_the_demo_provider_is_labelled_as_a_demo_model`; the fake chat model's Knowledge Search path (13-02 `test_the_default_fake_chat_model_searches_once_with_the_visitors_question`) still passes. |
| 2 | Agentic Draft save refused, with field and reason, when the effective model lacks tool support | `validation._tool_problems`; the two refusal tests (Default Model at `retrieval.mode`, override at `behaviour.model.model`). |
| 3 | At reply time an Agentic Agent whose effective model lacks tool support runs as Automatic and the Trace warns, in the Trace drawer | `save_question`, `Message.automatic_fallback`, `TraceOut.automatic_fallback`; Playground and widget API tests; `AgentPage.test.tsx` warning test. |
| 4 | The model picker marks models that support tools | `ChatModelOptions` in the Model override and Default Model pickers; `DraftEditor.test.tsx`, `ModelsPage.test.tsx`. |
| 5 | Design system; palette ratchet passes | `Notice`, `text.muted`, `text-muted`; no palette classes; [frontend-checks.log](frontend-checks.log): "0 palette-class uses". |
| 6 | Tests at the highest seam; 100% line and branch coverage | Seams above; [backend-tests.log](backend-tests.log), [frontend-checks.log](frontend-checks.log). |
| 7 | Glossary / ADRs | `GLOSSARY.md`: new **Tool support** and **Automatic fallback**; **Trace** mentions the warning. ADR-0015 is unchanged: the decision is as the spec states it. |

## Results

RESULTS_TABLE

## End-to-end (deferred)

Not run here, by instruction: Playwright runs once on the integrated branch. The specs lint, typecheck and list (`pnpm e2e --list`: 120 tests in 65 files, see [e2e-list.log](e2e-list.log)). That run must cover:

- `frontend/e2e/tests/playground.spec.ts` › "an Agentic Agent whose Default Model can't use tools answers as Automatic, and the Trace says so" (new: Bedrock access keys through the API, Default Model moved to Mistral 7B Instruct, the Agentic Draft refused, the Model override picker's "No tools: Automatic only" group, an answer with no Search and the Trace warning, axe).
- `frontend/e2e/tests/models.spec.ts` (extended: the Anthropic models sit in the "Supports tools" group).
- Regression: `playground.spec.ts` (all three), `agent-config.spec.ts`, `agent-drafts.spec.ts`, `bedrock-credentials.spec.ts`, `credentials.spec.ts`, `conversations.spec.ts`, `seed.spec.ts`, `five-minute-demo.spec.ts` (model pickers, Draft saves and the Trace drawer they touch).

## Notes

- Migration `0041_automatic_fallback` follows `0040_searches`; sibling 13-0x tickets adding migrations in parallel will need their `down_revision`s chained when integrated.
- When 13-09 makes Agentic the default, a new Agent's default Draft in an Organisation whose Default Model lacks tool support would be refused on its first save; 13-09 should decide how new Agents start there.
- Bedrock chat models still have no live adapter (`gateway/live.py`), as before this ticket; Mistral 7B Instruct is listed like the other Bedrock chat models.
