# Evidence: ticket 10-02, Seeded history

Branch `ticket/10-02-seeded-history`, from `origin/candidate` at `527d5d6` (07-04 Rollups and Version KPIs merged; 10-01 and 10-03 already in). The claim commit `2ffc0f3`, the first on the branch, set Status `in-progress`. The feature is `1316cab`; `45597d2` adds the edge-case tests and the check scripts in this folder. This ticket adds **no migration**.

**Status: done.** Every criterion is met and evidenced below. Gaps and best guesses are at the end.

## What was built

- **`backend/app/seed/history.py`** (new): the Seeded history. A fresh `make seed` swaps the app's Clock port for a `ShiftedClock` set four weeks back (06:00 UTC, 28 days ago) and moves it forward through the story, so everything the platform stamps from the Clock port (Audit Events, Versions, Live History, feedback, ratings, Token Budget days) is historical by construction. The story, day by day through the API:
  | Days ago | What happens (who) |
  |---|---|
  | 28 | Organisation set up (the 10-01 foundation); Instructions v1 "House style"; Product FAQ and Low-budget helper v1 (10-03); HR helper v1 (Owner) |
  | 17 | HR helper v2 "Shorter answers, without citations": one-sentence prompt, top-k 1, citations off (Editor) |
  | 10 | HR helper reverted to v1 (Owner) |
  | 6 | Instructions v2 "No promises beyond policy"; bulk-published to the Low-budget helper only, so the Product FAQ is **behind** (Owner) |
  | 3 | HR helper v3 "Cite the handbook and point to HR contacts", pinning Instructions v2 (Editor) |

  Every day from day 28 to yesterday, Visitors open the widget (shell → bootstrap token → Conversation token) for the HR helper (5 a day) and the Product FAQ (3 a day) at random times 09:00–18:00, ask 1–3 questions from a fixed list (`content.QUESTIONS`) through `POST /api/widget/agents/{id}/messages`, i.e. the real runtime, retrieval with Tag scoping and the input Guardrail, answered by the demo provider's `FunctionModel` (the Demo model), and give thumbs and Conversation Ratings through the widget API. Choices come from `random.Random(1002)` with each Version's `Reception` (`content.RECEPTION`): v1 74% up, **v2 42% up and low ratings**, v3 84% up. v3 is Live for three days only, so it is the **small-sample** Version.
- **Backfill**, the only direct writes: after each Conversation, its and its Messages' `created_at` (and `last_activity_at`) are set to the clock's times, feedback and rating rows' `created_at` to the times the Clock port gave them; after the story, the foundation's Organisation, Project, Documents, Tags, Agents and credentials get the history's start time. Append-only tables are never updated.
- **Rollups**: `app.analytics.rollup.roll_up` (what the Beat task runs) is called at 00:05 after each historical day, finalising it.
- **`runner.seed`**: decides "fresh" by whether the demo Owner's account exists; publishes Instructions v1 when the Project has none (before the Agents, so they pin it); waits for ingestion (`wait_for_documents`, needed in compose where the worker ingests); plays the history only when fresh, so **seeding again never replays it** (the existing idempotence tests still hold); refuses a non-fresh Demo Organisation whose HR helper has no Versions ("run `make seed-reset`"); always restores the app's clock. The history always runs on the Demo model: a real credential from `SEED_CREDENTIAL_*` becomes the Default Model only after it, so it is never billed for the history. `history=` (a `content.History`) sets the volume; tests use lighter ones.
- **`backend/app/seed/client.py`** (new): the seed's HTTP client (`SeedApi`, `SeedError`, `new_client`), moved out of `runner.py` so `history.py` can share it. `content.py` holds the story's data; the HR helper's Draft is v3's, so seeding again doesn't change it.
- **Docs**: `GLOSSARY.md` (new **Seeded history**; **Demo Organisation** updated), ADR-0012 (the shifted clock and the backfill exception, and the rejected "insert rows directly" option), `seed/README.md` (the timeline).

## Test seams

From the [shared test seams](../../../specs/README.md#shared-test-seams) and spec 10's Testing Decisions ("run the seed against a fresh test database and assert what an interviewer would see through the API: … both Agents are Live at the expected Versions, Live History shows the revert, Instructions show one Agent behind, analytics return the intended v1/v2/v3 ordering with intervals, … and Audit Events are present"; "running the seed twice yields the same counts"). Not confirmed with a human (none available); they are the seams the spec names.

- **API seam:** `backend/tests/integration/test_seeded_history.py` (7 tests, new), in process against real Postgres and Redis, signed in as the printed demo Owner; `test_seed.py` and `test_demo_pages.py` (10-01/10-03) now run with a quiet history (Versions, no Conversations) through the `quiet_seed_history` fixture.
- **Unit seam** (the clock and the ingestion wait, which in-process tests can't reach because ingestion is eager there): `backend/tests/unit/test_seed_history.py` (5 tests).
- **End-to-end:** the existing Playwright specs run after `make seed`, which now plays the full history in the compose stack (worker ingestion, local input classifier, Demo model); see Results.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | There's an HR Agent and a FAQ Agent with Tag scoping; HR has v1 to v3, with v2 reverted | `test_seeded_history.py::test_the_hr_agent_has_three_versions_with_v2_reverted`: HR Live v3, Versions [3, 2, 1], Live History `[publish 1→3, revert 2→1, publish 1→2, publish →1]`, oldest more than 27 days ago, newest more than 2 days ago, Editor/Owner as actors, Draft = v3. Tag scoping: `test_seed.py::test_the_seed_builds_the_demo_organisation_through_the_api` (HR helper scoped to HR, Product FAQ to Products; unchanged, still passing). Values from a full seed: [interviewer-view.json](interviewer-view.json) `agents.*.live_history`. |
| 2 | Instructions have v1 and v2, with one Agent behind | `test_the_instructions_have_two_versions_with_the_product_faq_behind`: Versions [2 "No promises beyond policy", 1 "House style"], v2 Current; rollout `behind: 1`: HR helper (v3, Instructions v2), Product FAQ (v1, Instructions **v1, behind**), Low-budget helper (v2 by `bulk_publish`, Instructions v2); no Draft changes. |
| 3 | Weeks of Conversations are generated through the runtime with a `FunctionModel`, timestamps are backfilled, and feedback and ratings come from a fixed random seed that makes v2 worse; one Version has a small sample | `test_an_interviewer_sees_four_weeks_of_history_that_tells_the_v2_story` (full history): Conversations on **each of the 28 days** (`created_at` from the Conversations viewer API), none today; every reply counted with tokens and no fallback; thumbs-up rate v2 < v1 < v3 with **v2's Wilson interval entirely below v1's**; mean rating v2 < v1; v1 and v2 not low-confidence; **v3 low-confidence** (< 30 Conversations) with its interval overlapping v1's. `test_the_history_is_answered_by_the_demo_model_even_with_a_real_credential` (every reply's `model_provider` is `demo`; the real credential is the Default Model afterwards). `test_seeding_again_never_replays_the_history` (same Conversations, Live History, Instructions and Audit count; the app's clock restored). Full seed numbers ([interviewer-view.json](interviewer-view.json)): HR v1 90 Conversations, 73% up [0.64, 0.81], rating 4.0; **v2 35, 36% up [0.24, 0.51], rating 2.3**; v3 15, 90% up [0.70, 0.97], **low confidence**; Product FAQ 84, 77% up; 224 Visitor Conversations in all. In compose: [history-in-compose.log](history-in-compose.log). |
| 4 | Rollups run for every historical day, and Audit Events are present | Same interviewer test: `usage_rollup_state.finalised_through` = yesterday and `usage_daily` holds exactly the 28 days with Conversations; the metrics API for the first day alone gives v1 5 Conversations (from the final rollup); the Audit tab API holds `organisation.created`, `project.instructions_published`, `agent.published`, `agent.reverted`, `agent.bulk_published`, `project.agents_bulk_published`, the oldest on the history's first day. [interviewer-view.json](interviewer-view.json) `audit_events`. |
| 5 | An API-level test asserts what an interviewer would see | `test_an_interviewer_sees_four_weeks_of_history_that_tells_the_v2_story`, plus criteria 1 and 2's tests, all through the Studio API as the demo Owner (the rollup-state check is the one database read). |
| 6 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams as above. Edge cases: `test_the_seed_will_not_complete_a_demo_organisation_without_its_history`, `test_the_seed_stops_when_a_visitor_gets_no_reply` (the clock is restored after a failure), unit tests for the clock and `wait_for_documents` (waits, failed Document, timeout). Backend coverage gate: see Results. |
| 7 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: **Seeded history** (with _Avoid_), **Demo Organisation** updated. ADR-0012 extended: the history goes through the API under a shifted clock; backfilling database-stamped timestamps is the one direct write; considered option "insert the history's rows directly". |

## Results

All runs are local and one at a time (GitHub Actions is down; the user authorised merging on local results). **Every check below ran from a fresh `git clone` of the pushed branch at `45597d2`** (`clean1002`, `git status` empty before and after); each log's first line names its command, commit and checkout. [run-checks.sh](run-checks.sh) is the sequence (install, lint, client drift, frontend, backend with fresh `rag1002-pg/redis/rustfs` containers, infra, security), then [run-e2e.sh](run-e2e.sh) (images, then the compose stack `rag1002-e2e`, a timed `make seed`, Playwright). Images, containers and volumes were removed afterwards. `origin/candidate` was still `527d5d6` when the checks ran and when this was committed, so no merge was needed; this ticket adds no migration, so the numbering is untouched. Commits after `45597d2` change only this folder and the ticket file.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `make install` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | exit 0, "API client is up to date.", `git status` empty (no API change) | [client-drift.log](client-drift.log) |
| Frontend tests + coverage gate | `make test-frontend` | exit 0: **57 files, 779 tests**; 100% statements and branches | [frontend-tests.log](frontend-tests.log) |
| Backend tests + coverage gate | `make test-backend` | **2399 passed, 1 error**, 24 deselected (live); **100.00%** lines and branches (11300 statements, 1374 branches, coverage gate reached). The error: `test_tenant_isolation.py::…[DELETE …/tags/{tag_id}]` at **setup**, `redis.exceptions.TimeoutError: Timeout connecting to server` (the shared machine under load; 10-02 touches neither the test nor tags). Make exited 2 for it. | [backend-tests.log](backend-tests.log) |
| Backend rerun of that file | `uv run pytest --no-cov tests/integration/test_tenant_isolation.py`, fresh containers, same clone | **exit 0: 671 passed** | [backend-tenant-isolation-rerun.log](backend-tenant-isolation-rerun.log) |
| Infra | `make infra-check` | exit 0; Checkov 288 passed, 0 failed (unchanged by this ticket) | [infra-check.log](infra-check.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` | exit 0 both | [security.log](security.log) |
| Images | [build.sh](build.sh) (sandbox `make images`: `WITH_PDF=false`, `BUNDLE_MODELS=true`) | exit 0 | [images.log](images.log) |
| End-to-end | stack up, **`time make seed` (full history: real 2m21s)**, then Playwright `seed`, `demo-pages`, `embed`, `token-budget`, `operational-settings`, `widget-lifecycle`, `widget-accessibility`, `branded-widget`, `smoke`, `auth` with [compose.sandbox.yml](compose.sandbox.yml) and [e2e.env](e2e.env) (CI settings: one retry) | **exit 0: 24 passed** | [e2e.log](e2e.log) |
| History in compose | `psql` over the e2e stack after the seed: replies by Agent Version | HR v1 90 Conversations / 152 replies, v2 35 / 57, v3 15 / 25; Product FAQ v1 84 / 142: the same as the in-process seed (the fixed random seed) | [history-in-compose.log](history-in-compose.log) |

[interviewer-view.json](interviewer-view.json) is what the Studio API returns after a full in-process seed (worktree at `45597d2`, a throwaway dump test not committed): Live History, Version KPIs, the rollout, Audit Events and the newest Conversations.

## Gaps and best guesses

- **Best guesses, recorded instead of asking:**
  - **Four weeks** (28 days) of history, so the Studio's default 30-day range shows all of it; 5 HR and 3 FAQ Conversations a day, which keeps `make seed` to a few minutes in compose while giving v1 and v2 over 30 votes each.
  - **The HR helper is reached through the widget** (its shell is served to anyone; the browser enforces framing), though it has no Allowed Origins: it is the internal Agent, and Visitor Conversations are what analytics count.
  - **Instructions v2 is rolled out to the Low-budget helper by bulk publish**, so exactly one Agent (the Product FAQ) is behind, and the bulk action appears in Live History and the Audit tab.
  - **v2 is worse in configuration too** (terse prompt, top-k 1, no citations) so the story reads sensibly in the Version diff; with the Demo model the answers themselves differ only in citations, and the feedback probabilities carry the difference.
  - **Fresh = the demo Owner's account doesn't exist.** A Demo Organisation seeded before this ticket (HR helper without Versions) is refused with a pointer to `make seed-reset` rather than given a history after the fact.
  - **Version `created_at` and Audit Events are not backfilled**: they are stamped from the Clock port already. The 10-03 Agents are published at the history's start time.
- **Gaps:** no new Playwright spec for the history (spec 10's automated five-minute demo, which opens the comparison, is ticket 10-06); the existing seed and demo-pages specs ran after the full seed. Version rating means for v2 and v3 are "low confidence" (fewer than 30 ratings): thumbs carry the confident comparison.
