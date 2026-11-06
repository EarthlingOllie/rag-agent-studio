# Evidence: ticket 04-08, Playground errors and reset

Branch `ticket/04-08-playground-errors-reset`, from `origin/candidate` at `00f8214` (04-01, the only blocker, and everything after it merged). The claim commit `8d36906`, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to other tickets, plus best guesses recorded instead of asking.

## What was built

When the model provider fails, the Playground says why; an Editor can reset the Playground to a fresh Conversation.

- **Provider errors** (`backend/app/runtime/errors.py`, new). `provider_error` turns a provider failure into an `ErrorEvent(kind, message)` with one of four kinds (`ProviderErrorKind`):

  | Code | Raised for | Message |
  |---|---|---|
  | `invalid_key` | Pydantic AI `ModelAuthenticationError`; any `ModelHTTPError` 401/403 | The provider rejected the API key. An Owner can check or rotate the Provider Credential in Settings, Provider Credentials. |
  | `rate_limited` | `ModelRateLimitError`, `ModelQuotaExceededError`; HTTP 429/402 | The provider says this key is over its rate limit or quota. Wait a moment and try again, or check the provider account's limits and billing. |
  | `model_unavailable` | `ModelNotFoundError`, `ModelUnavailableError` (incl. overloaded); HTTP 404; the gateway can't build the chat model (`ModelUnavailableError`, `UnsupportedCredentialError`) | The model {model} isn't available from the provider right now. Try again later, or choose another model for the Draft or the Default Model. |
  | `provider_error` | any other `ModelAPIError` (5xx, connection, timeout, rejected request) or `UnexpectedModelBehavior` | The provider couldn't answer just now. Try again in a moment. |

  The failure is logged by kind, error class and status code only (never the provider's error body).
- **Runtime** (`app/runtime/runtime.py`). `run_turn` catches provider errors while retrieving and answering and ends the turn with the `ErrorEvent`; no `DoneEvent` follows. It still knows nothing about HTTP, so spec 06's widget gets the same typed event.
- **Playground** (`app/playground/service.py`, `api.py`). A gateway failure building the chat model also becomes an `ErrorEvent`. The stream ends with one `event: error` / `data: {"code": …, "message": …}`. No answer Message is saved, so the failed question is never among the remembered turns (`_turns` skips an unanswered question). The OpenAPI description of the stream lists the event and its codes; the client is regenerated.
- **Fake chat model** (`app/gateway/fakes.py`). As with the canary leak prompt, a question containing "simulate an invalid key", "simulate a rate limit" or "simulate an unavailable model" makes the fake raise the error Pydantic AI raises for it, so end-to-end tests can drive each failure without a real provider.
- **Studio** (`frontend/apps/studio/src/projects/agents.ts`, `AgentPage.tsx`).
  - `askPlayground` turns an `error` event into a `ProviderError` (typed `code`); `agentFailure` shows its message in the Playground's alert. The half-streamed answer is dropped; the question stays.
  - A **Reset conversation** button starts a new Playground Conversation (`POST …/playground/conversations`), clears the messages, the error and the Trace drawer, and says "Started a new conversation." in a status region. The next question goes to the new Conversation. It is disabled while an answer streams; a refused start shows the API's reason.
- **Remembered turns**: unchanged code (`list(turns)[-remembered_turns:]`, 0 means none, at most 20); this ticket adds tests that verify the truncation (criterion 3).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams) and the spec's Testing Decisions ("provider errors become a typed error event in the stream"; "remembered turns are truncated correctly"; "error events show the right message"). No human was available to confirm the seams, so the ones the spec names were used.

- **API seam** (in process, real Postgres with pgvector and Redis): `backend/tests/integration/test_playground_errors.py` (new). The chat model is a Pydantic AI `FunctionModel` raising the errors Pydantic AI's provider models raise (the adapter fake the seams table names), or the gateway's own fake adapters as the compose stack runs them.
- **Frontend network seam (MSW):** `frontend/apps/studio/src/projects/AgentPage.test.tsx`; the MSW stream helper in `src/test/agents.ts` can end with an `error` event, and each start returns a new Conversation ID.
- **End-to-end** against the docker compose stack with the fake gateway: `frontend/e2e/tests/playground-errors.spec.ts` (new).

Each behaviour was driven test-first: the first API test failed with the raw `ModelAuthenticationError` escaping the stream; the frontend tests failed (no alert text, no Reset button) before `ProviderError` and the button existed; the fake-simulation tests failed (an answer instead of an error) before `FAKE_FAILURES`. The reset and truncation API tests pass on the existing endpoints: they verify behaviour the API already had, which this ticket relies on.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Provider errors become typed error events with readable messages | **Code:** `app/runtime/errors.py`, `run_turn`, `answer` in `app/playground/service.py`, the `error` event in `app/playground/api.py`.<br>**API tests** (`test_playground_errors.py`):<br>• `test_an_invalid_key_ends_the_stream_with_a_typed_error_event`: the whole stream is exactly `[("error", {"code": "invalid_key", "message": …})]`.<br>• `test_each_provider_failure_has_its_own_code_and_message` (11 cases): rate limit and quota → `rate_limited`; not found and overloaded → `model_unavailable` naming the model; plain HTTP 403/429/404/500/400, a connection error and invalid model output map by status to their code, each with its exact message.<br>• `test_a_failure_mid_answer_ends_the_stream_with_the_error_and_saves_no_answer`: tokens, then the `error` event; the Conversation reads back with the question and no answer.<br>• `test_a_question_the_provider_failed_on_is_not_remembered`: after a failure the next answer remembers only the answered turn.<br>• `test_a_chat_model_the_gateway_cant_build_is_unavailable`: `model_unavailable` for `gpt-4.1-mini`.<br>• `test_the_fake_chat_model_simulates_each_provider_failure_on_request` (3 cases).<br>**Frontend** (`AgentPage.test.tsx`):<br>• `a provider failure shows why, and the half-streamed answer is dropped`<br>• `a %s error event shows its message` (invalid_key, model_unavailable, provider_error)<br>**E2E** (`playground-errors.spec.ts`): after a real answer, "simulate a rate limit", "simulate an invalid key" and "simulate an unavailable model" each show their message in the alert and add no answer; axe scan clean. |
| 2 | Reset starts a new Playground Conversation | **Code:** `reset` and the **Reset conversation** button in `AgentPage.tsx`.<br>**API test:** `test_a_reset_playground_starts_a_new_conversation_that_remembers_nothing`: the new Conversation has a new ID, is flagged Playground, is empty, and its first answer remembers nothing; the earlier Conversation is kept and still remembers its own turns.<br>**Frontend:**<br>• `resetting the Playground starts a new Conversation`: messages and the Trace drawer are cleared, "Started a new conversation." is announced, and the requests are start, ask (first ID), start, ask (new ID).<br>• `a reset clears an error shown before it`<br>• `a reset that can't start a new Conversation says why`<br>• `the Playground can't be reset while an answer streams in`<br>**E2E:** Reset conversation sends `POST …/playground/conversations` (201, no messages), the list empties, the next question goes to `…/conversations/{new id}/messages`, and the new Conversation reads back as Playground with exactly that question and its answer; axe scan clean. |
| 3 | Truncation to the configured number of remembered turns is verified | **API tests** (`test_playground_errors.py`):<br>• `test_the_remembered_turns_are_the_most_recent_ones_as_the_conversation_grows`: with 3 remembered turns, six questions see `[]`, `[Q1]`, `[Q1,Q2]`, `[Q1,Q2,Q3]`, `[Q2,Q3,Q4]`, `[Q3,Q4,Q5]`.<br>• `test_the_remembered_turns_reach_the_model_as_whole_question_and_answer_pairs`: with 1, the model gets the last question and the answer it gave, nothing older.<br>• `test_remembered_turns_are_capped_at_twenty`: 21 is refused (422), 20 saves.<br>• `test_a_question_the_provider_failed_on_is_not_remembered` (above).<br>Existing: `test_playground.py::test_only_the_remembered_turns_reach_the_model` (2 keeps two, 0 none), `test_an_unanswered_question_is_not_remembered`. |
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams above; results below. Backend gate `fail_under = 100` with branch coverage; frontend Vitest gate 100% statements, branches, functions and lines. |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` (after **Playground Conversation**) gains **Playground reset** and **Provider error**. No ADR changed: model calls still go through the gateway, and the runtime stays transport-agnostic. |

## Results

All runs are local and sequential, on `abf5acb` (the implementation commit; `origin/candidate` was still `00f8214` when they finished, so no merge was needed). This evidence commit changes only the ticket, this folder and nothing that is built or tested. GitHub Actions is down; the user authorised merging on local results.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against fresh `rag0408-pg` (pgvector), `rag0408-redis` and `rag0408-rustfs` containers | **1500 passed**, 7 deselected (live); coverage **100%** lines and branches (7057 statements, 790 branches) | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **38 files, 474 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | gitleaks over this branch's commits not on candidate; `make audit` (pip-audit, pnpm audit) | no leaks found; no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0408`), on the images just built | **57 passed** first run, including `playground-errors.spec.ts` and `playground.spec.ts` | [e2e.log](e2e.log) |
| Infra | not run | this branch changes nothing under `infra/` | |

## Gaps and best guesses

- **Provider Embedding Models in the Playground (pre-existing, not this ticket).** Playground retrieval only has the local embedders (`IngestionPorts.embedders`), so a Project on a provider Embedding Model (03-09) raises `EmbeddingModelUnavailableError` when asked, before this ticket and after. `run_turn` already turns a provider failure while retrieving into an error event, so once retrieval resolves provider embedders through the gateway their failures are reported the same way. Left to the owner of retrieval with provider Embedding Models.
- **Best guesses, recorded instead of asking:**
  - **Four codes.** The three the spec names plus `provider_error` for anything else (5xx, timeouts, connection errors, invalid model output), so every provider failure gets a readable message rather than a broken stream. An exhausted quota counts as `rate_limited` (the spec groups "rate limited"; the message mentions quota and billing), and an overloaded model as `model_unavailable`.
  - **Messages are generic about the credential** (they don't name it) because the failing call may be the chat model or another provider call in the turn; the model-unavailable message names the model the provider reported.
  - **The failed question is kept** in the Conversation, unanswered, as a record of what was asked; it is not remembered, and no answer or cost is saved for it.
  - **Partial text is dropped** in the Studio when the error arrives mid-answer, so a half answer is never mistaken for a whole one.
  - **Reset is a new Conversation**, not deleting the old one: Playground Conversations are recorded (spec 04), so the old one is kept. Reset starts the new Conversation at once (not lazily on the next question), so "Reset starts a new Playground Conversation" is literally true and a failure to start is shown immediately.
- **Sandbox limits:**
  - Images were built with `WITH_PDF=false BUNDLE_MODELS=false` and the egress proxy CA (`build.sh`), as earlier tickets did.
  - E2E ran against a compose project on moved ports (`compose.sandbox.yml`, 42xxx) beside other tickets' stacks.
  - No real provider was called: the fake verifier and the fake gateway were used throughout.
