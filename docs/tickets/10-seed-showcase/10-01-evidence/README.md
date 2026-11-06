# Evidence: ticket 10-01, Seed foundation

Branch `ticket/10-01-seed-foundation`, from `origin/candidate` at `a8eedee` (03-06, 02-05 and 04-07, the blockers, all merged). The claim commit `577918a`, the first on the branch, set Status `in-progress`. `origin/candidate` at `05e1a18` (04-06) was merged in, and every check below ran on the merged tree at `1ea05d8`. Only this README, the logs and the ticket's Status changed after that.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to later spec 10 tickets on purpose, plus best guesses recorded instead of asking.

## What was built

- **`make seed` / `make seed-reset`** (`Makefile`). Each runs `python -m app.seed` (`backend/app/seed/__main__.py`) in a one-off API container beside the running stack:
  - the repo's `seed/` folder is mounted at `/seed`;
  - files go to RustFS by its internal address;
  - migrations are applied first;
  - the sign-in details are printed at the end.
  - `make e2e` now seeds before Playwright runs.
- **The seed** (`backend/app/seed/runner.py`, content in `content.py`) drives the platform's own HTTP API in process, as a person in the Studio would:
  - sign up the demo Owner, which creates "Northwind Traders";
  - invite and sign up the Editor;
  - add the demo credential (and a real one, if given) and set the Default Model;
  - save the Theme;
  - create the "Northwind Handbook" Project and the Tags HR and Products;
  - upload four Documents through presigned URLs and confirm them, then tag them;
  - create the Agents "HR helper" and "Product FAQ", each scoped to its Tag.
  - **Idempotent:** it finds the Demo Organisation through the demo Owner's account, and only adds what is missing or changes what differs (Theme, Default Model, Document Tags, Agent Drafts).
- **Reset** (`erase_demo` and `reset`, plus `backend/app/tenancy/erasure.py`):
  - It erases only the Organisation that the demo Owner owns under the demo name: every tenant row (by cascade), its Audit Events and its stored files.
  - It then removes the demo accounts and seeds again. An account that another Organisation's Audit Events name is retired instead of deleted (unusable email and password).
  - It refuses, erasing nothing, while a demo account still belongs to another Organisation.
  - Migration `0023_erase_organisation` lets the append-only audit trigger pass a DELETE only for the Organisation that the transaction names in `app.erasing_organisation`.
- **Demo provider** (`Provider.DEMO` in `app/credentials/registry.py`, adapter `app/gateway/demo.py`):
  - It is named "Demo (not a real model)" and has one chat model, "Demo model" (`demo-chat`), priced at 0.
  - The model is a deterministic Pydantic AI `FunctionModel`. It answers with the first retrieved Chunk, quoted and cited `[C1]`, and every answer starts "Demo model (canned answer, not AI)".
  - The live and the fake adapters both build it. The live credential verifier passes it without calling anyone.
  - The Studio labels the provider "Demo: canned answers, not a real model" on the Credentials page, the Models page and the Agent editor's model pickers.
- **Content** (`seed/`):
  - `documents/`: the staff handbook (md, HR), the returns policy (md, Products, with a planted injection in its footnote), the product FAQ (docx) and the spring range slide deck (pptx).
  - `sources/`: the markdown the docx and pptx are made from by `backend/tests/fixtures/make_seed_documents.py`.
  - `LICENCE.md`: CC0, synthetic.
  - `README.md`: the demo accounts and how to seed.
- **Real credential:** `SEED_CREDENTIAL_PROVIDER` (anthropic or openai) plus `SEED_CREDENTIAL_API_KEY`, and optionally `SEED_CREDENTIAL_MODEL`. The seed adds the credential and makes it the Default Model; the demo credential stays.
- **Docs:**
  - `GLOSSARY.md`: Demo Organisation, Demo model.
  - ADR-0012 (`docs/adr/0012-demo-seed-through-the-api.md`): seeding through the API, the demo provider, and the one audit-erasure exception.

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams) and spec 10's Testing Decisions. No human was available to confirm the seams, so the ones the spec names were used.

- **API seam:** `backend/tests/integration/test_seed.py` (new: 20 tests, 26 cases).
  - The seed runs against the test database (real Postgres and Redis). Everything is asserted through the API, signed in with the printed demo accounts.
  - Documents are converted by real Docling (Markdown, DOCX and PPTX need no models). Embeddings use the hash fake.
  - One test runs the whole seed against RustFS, through real presigned PUTs.
  - The command line (`main`) is run in process.
  - Audit counts are read from the table, the one thing the API can't count.
- **Model gateway seam:** `backend/tests/unit/test_model_gateway.py`. The demo provider is built through the gateway with the fake adapters and with the live ones; the live ones use a transport that fails if anything is called.
- **Credential verifier:** `backend/tests/unit/test_http_credential_verifier.py`.
- **Frontend network seam (MSW):** `frontend/apps/studio/src/settings/ModelsPage.test.tsx`, with the demo label in the current Default Model and in the picker.
- **End-to-end:** `frontend/e2e/tests/seed.spec.ts` (new), against the docker compose stack after `make seed`, with axe checks.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | The seed goes through application services, is idempotent, and `seed-reset` recreates only the demo Organisation | **Through the API:** `runner.py` calls only HTTP endpoints, except the erasure in reset, which no endpoint offers (ADR-0012).<br>• `test_the_seed_builds_the_demo_organisation_through_the_api`<br>• `test_files_go_to_the_object_store_through_presigned_urls` (RustFS; every Document Ready)<br>**Idempotent:**<br>• `test_seeding_twice_changes_nothing`: same report, and the same members, credentials, Documents (edition 1), Tags, Agents and Audit Event count.<br>• `test_seeding_again_puts_back_what_was_changed`: a deleted Tag and Document, a changed Theme, an unscoped Agent and a different Default Model are all restored.<br>• `test_the_command_seeds_resets_and_prints_the_sign_in_details`<br>**Reset:**<br>• `test_reset_recreates_only_the_demo_organisation`: after a Playground Conversation, reset gives a new Organisation ID with the same contents. The old Organisation's Audit Events and its stored files are gone, and the old sessions get 401. A bystander Organisation keeps its Project and its exact Audit Event count.<br>• `test_reset_with_no_demo_organisation_just_seeds`<br>• `test_reset_refuses_while_a_demo_account_belongs_to_another_organisation`: nothing is erased. Once the Editor leaves, reset works, and the other Organisation's Audit Events still name the old Editor (the account was retired).<br>• `test_audit_events_stay_append_only_outside_an_erasure`; `test_migrations.py` round trip.<br>**Real stack** ([make-seed.log](make-seed.log)): a second `make seed` left the counts unchanged (36 Organisations, 13 Documents, 120 Audit Events). `make seed-reset` gave a new demo Organisation ID with the same counts. All four Documents were Ready after the worker ingested them with Docling. |
| 2 | A demo provider adapter is clearly labelled as a demo model | **Gateway** (`test_model_gateway.py`):<br>• `test_the_demo_model_answers_from_the_first_retrieved_chunk[fake adapters/live adapters]`: exact answer, streamed word by word, nothing called.<br>• `test_without_a_chunk_the_demo_model_says_it_doesnt_know`<br>• `test_the_demo_provider_is_labelled_as_a_demo_model`<br>**Verifier:** `test_the_demo_provider_passes_without_calling_anyone`.<br>**API:** `test_the_demo_model_is_labelled_and_answers_without_any_api_key`. The Default Model is `demo`/`demo-chat`/"Demo model" and the provider is named "Demo (not a real model)". A Playground answer starts "Demo model (canned answer, not AI): from northwind-…" and streams a `C1` citation.<br>**Registry and price table:** `test_provider_credentials.py` and `test_prices.py`.<br>**Studio:** `the seeded demo model is labelled as a demo, not a real model` (MSW).<br>**E2E:** `seed.spec.ts` "the demo model is the Default Model, labelled as a demo" sees "Demo model, using Northwind demo model (Demo: canned answers, not a real model)". |
| 3 | Owner and Editor accounts are created and their sign-in details printed | **Tests:**<br>• `test_the_owner_and_editor_sign_in_with_the_printed_details`: the printed lines hold both emails and passwords and the Studio URL; both accounts sign in, as Owner and Editor.<br>• `test_the_seed_builds_…`: members `{owner: owner, editor: editor}`.<br>• `test_the_command_…` checks stdout.<br>**Docs:** `seed/README.md` lists them.<br>**Real stack:** [make-seed.log](make-seed.log) shows the printed block. In `seed.spec.ts` the Owner and the Editor sign in with those details. |
| 4 | The Northwind Project has synthetic Documents (one with an injection footnote) with a licence note, plus Tags and a Theme | **Tests:**<br>• `test_the_seed_builds_…`: four Documents, all Ready with Chunks. They are tagged HR ×1 and Products ×3, the deck's slide text is a Chunk, the Agents are scoped to their Tags, and the Theme is olive and Lora.<br>• `test_one_document_has_a_planted_injection_in_a_footnote`: exactly one Chunk across all Documents holds the payload, in `northwind-returns-policy.md`.<br>• `test_the_seed_content_is_synthetic_and_freely_licensed`: `seed/LICENCE.md` is CC0, says the content is synthetic, and lists every seeded file.<br>**E2E:** `seed.spec.ts` "the demo Owner finds Northwind's Project, Documents, Tags and Agents" checks each Document Ready with its Tag, the axe scan is clean, and both Agents are listed. |
| 5 | A real credential can optionally be read from the environment | **Tests:**<br>• `test_a_real_credential_is_read_from_the_environment` (5 cases: none, blank, Anthropic default model, OpenAI default model, explicit model).<br>• `test_a_half_set_or_unusable_real_credential_is_refused` (3 cases).<br>• `test_a_real_credential_can_answer_instead_of_the_demo_model`: "Northwind OpenAI" is added beside the demo credential and becomes the Default Model, idempotently.<br>• `test_the_command_reports_why_it_failed`: exit 1 with the reason.<br>**Make:** `make seed` passes `SEED_CREDENTIAL_*` into the container. |
| 6 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | **Backend:** 1242 passed, coverage 100.00% (6259 statements, 652 branches) ([backend-tests.log](backend-tests.log)).<br>**Frontend:** 378 tests passed with the 100% thresholds ([frontend-tests.log](frontend-tests.log)).<br>**E2E:** 51 passed ([e2e.log](e2e.log)). |
| 7 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Glossary:** "Demo Organisation" (Tenancy) and "Demo model" (Models).<br>**ADR:** ADR-0012 records the decisions (through the API, the demo provider, the audit-erasure exception, and why no slug column). |

## Checks

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage | `make test-backend` (`uv run pytest`) against Postgres, Redis and RustFS containers on moved ports | 1242 passed, 7 deselected (live), 100.00% | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage | `make test-frontend` | 35 files, 378 tests passed | [frontend-tests.log](frontend-tests.log) |
| Lint and types | `make lint` (ruff, ruff format, mypy strict, eslint, tsc) | clean | [lint.log](lint.log) |
| API client drift | `make check-client` | up to date | [client-drift.log](client-drift.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag1001`), which includes `make seed` | 51 passed, including `seed.spec.ts` | [e2e.log](e2e.log) |
| Seed on the stack | `make seed` again, `make seed-reset` | idempotent, reset recreates | [make-seed.log](make-seed.log) |

## Gaps and best guesses

- **Left to later spec 10 tickets, on purpose:**
  - Versions, Live History, Project Instructions, historical Conversations and analytics (10-02).
  - The per-Agent Theme override and the low Token Budget Agent (spec 06, 10-03).
  - Demo host pages (10-03), the attack panel (10-04), seeding in AWS (10-05), and the README with the automated five-minute demo (10-06).
  - The injection footnote is seeded and is a Chunk. Flagging it in the viewer is the ingestion scan's job (03-07, built in parallel).
- **No PDF in the seed set.** The spec mentions markdown converted to PDF, DOCX and PPTX. Docling's PDF pipeline needs the layout models, which the test environment and images built `WITH_PDF=false` don't have, so a seeded PDF would sit Failed there. The four Documents the spec names (handbook, product FAQ, returns policy, slide deck) are md, md, docx and pptx.
- **Best guesses, recorded instead of asking:**
  - **The Demo Organisation is found through the demo Owner's account**, not a slug column. ADR-0012 gives the reason.
  - **Reset deletes Audit Events** of the demo Organisation through a narrow trigger exception. The alternative was leaving a retired Organisation behind on every reset.
  - **Demo passwords are fixed and published** ("northwind-owner-demo", "northwind-editor-demo"). This follows user story 7 (credentials shown on the README). Anyone deploying the demo publicly should reset or change them.
  - **The demo credential needs an API key field.** It is stored with the placeholder `demo-no-key-needed`, because the credential model and API are API-key shaped and the demo provider checks nothing.
  - **A real credential** only answers for real when the stack runs `MODEL_GATEWAY=live` (and `CREDENTIAL_VERIFIER=live`). `seed/README.md` says so.
- **Sandbox limits:**
  - Images were built with `WITH_PDF=false BUNDLE_MODELS=false` and the egress proxy CA (`build.sh`), as earlier tickets did.
  - E2E ran on moved ports (`compose.sandbox.yml`).
  - GitHub Actions is down, so every result here is local.
  - No real provider was called: the fake verifier and the fake gateway were used, and no `SEED_CREDENTIAL_*` was set on the stack.
  - Docker build cache shared with other tickets' builds was left in place. Containers, volumes and this ticket's images were removed.
