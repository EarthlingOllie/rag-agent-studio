# Evidence: ticket 13-08, Searches in metrics and retention

Branch `t/13-08`, from `aab4336c` (the integration branch: all of spec 12, plus merged `t/13-01`, `t/13-02`, `t/13-03` and `t/13-04`). The claim commit `43bc4caa` set Status `in-progress`; the change is commits `16510032` to `91bc8afb`. Every check below ran on `91bc8afb`; later commits only add this folder and tick the ticket.

**Status: done.** Every criterion is met and evidenced below. The Playwright run is deferred to the integrated branch (see [End-to-end](#end-to-end-deferred)).

## What was built

- **Usage rollups** (`backend/app/analytics/{models,usage}.py`, migration `0042_usage_searches`): each `usage_daily` row gains `searches`, the sum of its Version's Visitor replies' `search_count` that UTC day (a call the Search limit refused is not a Search, as 13-02 counts it). `Usage` adds them up across days; the live partial day is worked out from the raw Messages the same way. Playground replies never enter (the existing `_visitor_replies` filter).
- **Version KPIs** (`backend/app/analytics/{service,api}.py`): `VersionKpisOut` gains `retrieval_mode` (from the configuration the Version was published with) and `searches: {total, mean_per_reply}`; the mean is over every reply (so an Automatic Version's is 0), null without a reply.
- **Version comparison** (`backend/app/analytics/comparison.py`): a `searches_per_reply` row, "Mean searches per reply", unit `searches` (two decimals in the CSV), favouring neither Version (more searching costs more but may answer better), marked small sample with the Conversations. Both sides' KPIs carry `retrieval_mode`.
- **Retention** (`backend/app/retention/service.py`): `purge_messages`, shared by the daily purge, a Conversation deleted on request and an answer finishing after its Conversation was deleted, also clears the `query` of the purged Messages' Searches; the Searches, their order, latency, limit flag, Chunks and the Message's `search_count` stay, so the metrics read the same.
- **Studio** (design-system tokens and text recipes only; no palette classes, no `dark:`):
  - `projects/AnalyticsTab.tsx`: a "Searches per reply" KPI card: the mean, the Version's Retrieval Mode, and "N Searches in M replies".
  - `projects/VersionComparison.tsx`: the new row (two decimals), and both Versions' modes passed to the configuration diff.
  - `projects/AgentVersions.tsx`: each Version in the list says "Retrieval Mode: Automatic|Agentic"; the Compare section passes both Versions' modes when both sides are Versions.
  - `projects/AgentDiff.tsx`: `AgentDiffView` takes optional `modes`; a Version Diff given them is headed by a Retrieval Mode row ("Retrieval Mode: Automatic → Agentic", or "… Agentic in both"), and the `retrieval.mode` change is not listed twice. Draft Diffs are untouched (13-05 owns them); expect a merge in this file.
- **API client** regenerated (`frontend/packages/api-client`).
- **Glossary**: new term **Searches per reply**; Version KPIs, Usage rollup, Purge, Version comparison, Better side and Diff updated. No ADR changed (ADR-0015 stands).

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams) (spec 13 adds none); no human was available to confirm seams, so these are the pre-agreed ones.

- **API and task seam** (`backend/tests/integration/test_search_metrics.py`, widget Visitors answered by a scripted `FunctionModel` that makes `searches:N` Knowledge Searches; rollup and purge Beat tasks called as tasks; assertions on HTTP responses only):
  - `test_a_versions_kpis_show_its_searches_and_mean_searches_per_reply`: replies making 2, 1, 0 and 3 Searches give `{"total": 6, "mean_per_reply": 1.5}` and `retrieval_mode` `agentic`.
  - `test_the_rollup_records_the_search_count_per_version_per_day`: two days, each read back from its final rollup (Nov 5: 2 in 1 reply; Nov 6: 1 in 2 replies), the range sums them, and the rolled day equals the live day.
  - `test_playground_searches_stay_out_of_the_visitor_kpis`: Playground Searches on a rolled day and on the live day change nothing.
  - `test_a_version_without_replies_has_no_mean_and_an_automatic_one_searches_never`.
  - `test_comparison_shows_mean_searches_per_reply_and_each_versions_retrieval_mode`: Agentic v1 against Automatic v2: the row (1.5 against 0, difference −1.5, favours neither), both modes, the `retrieval.mode` change in the Version Diff, and the CSV line.
  - `test_the_version_list_gives_each_versions_retrieval_mode`.
  - `test_purging_message_text_also_purges_search_queries`: the daily purge clears an expired Visitor reply's and a Playground reply's queries, keeps a newer reply's, and the metrics are identical before and after.
  - `test_deleting_a_conversation_purges_its_search_queries`.
- **Existing tests extended where they spell out the whole shape**: the empty-KPIs dict in `test_version_metrics.py` and the metric list in `test_version_comparison.py` gain the new fields/row.
- **Frontend network seam (MSW)**: `AnalyticsTab.test.tsx` (the card for an Agentic, an Automatic, an unused and a one-reply Version; the comparison row "0.00 / 1.50 / +1.50", no better side; the configuration diff's "Retrieval Mode: Automatic → Agentic" shown once); `AgentDrafts.test.tsx` (`each Version in the history shows its Retrieval Mode`; `a Version Diff shows the Retrieval Mode of both Versions, once`, including "Agentic in both" and no row on a Draft Diff). Fixtures in `test/analytics.ts` gain the fields.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Usage rollups record a search count per Agent Version per UTC day | `usage_daily.searches`, migration 0042 (round trip and autogenerate check in `test_migrations.py`); `test_the_rollup_records_the_search_count_per_version_per_day` |
| 2 | Version KPIs and Version comparison show mean searches per reply | `SearchesOut`, `searches_per_reply` metric; API tests above; MSW card and comparison tests; e2e specs updated |
| 3 | The Version list and Version Diff show the Retrieval Mode | Version list returns each Version's config (`test_the_version_list_gives_each_versions_retrieval_mode`) and shows "Retrieval Mode: …"; Version Diff row in `AgentDiffView` (Versions view and Version comparison); MSW tests |
| 4 | Playground Messages stay out of the Visitor rollups | `test_playground_searches_stay_out_of_the_visitor_kpis` (rolled and live days) |
| 5 | Purging Message text also purges search queries | `purge_messages`; `test_purging_message_text_also_purges_search_queries`, `test_deleting_a_conversation_purges_its_search_queries` |
| 6 | New Studio UI uses the design system; palette ratchet passes | `KpiCard`, `text`, `table` recipes and tokens only; [frontend-checks.log](frontend-checks.log) |
| 7 | Tests at the highest seam; 100% line and branch coverage | Seams above; [backend-tests.log](backend-tests.log), [frontend-checks.log](frontend-checks.log) |
| 8 | Glossary / ADRs current | GLOSSARY.md: Searches per reply (new), Version KPIs, Usage rollup, Purge, Version comparison, Better side, Diff. ADRs unchanged. |

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `cd backend && TEST_DATABASE_URL=…/studio_test_t08 TEST_REDIS_URL=redis://localhost:6379/15 uv run pytest -n 3` (shared compose Postgres/Redis, several tickets running at once, load average ~17 on 4 CPUs) | **2582 passed**, 4 failed and 1 error (load timeouts, see below) in 77 min; coverage 99.97%: the only lines missed (`app/seed/runner.py` 94-96) are those the timed-out seed test covers | [backend-tests.log](backend-tests.log) |
| Load-timeout rerun, coverage combined | `uv run pytest --cov-append tests/integration/test_logging.py tests/integration/test_seed.py` alone, appending to the full run's coverage data | **36 passed**; combined coverage **100.00%** (12285 statements, 1536 branches), gate reached | [backend-load-rerun.log](backend-load-rerun.log) |
| Backend lint and types | `make lint-backend` (ruff check, ruff format --check, mypy --strict) | exit 0 (399 files) | [lint-backend.log](lint-backend.log) |
| API client drift | `make check-client` | up to date | [check-client.log](check-client.log) |
| Frontend | `pnpm test && pnpm check-embed-size && pnpm palette-ratchet && pnpm lint && pnpm typecheck` | **1096 passed** (84 files), 100% coverage, 0 palette-class uses, exit 0 | [frontend-checks.log](frontend-checks.log) |
| Links | `make link-check` | 2757 relative links in 275 files resolve | [link-check.log](link-check.log) |
| e2e listing | `pnpm exec playwright test --list` on the affected specs | 6 tests in 5 files list (typecheck and lint above cover them) | [e2e-list.log](e2e-list.log) |

**Failures under load, not caused by this ticket.** `tests/integration/test_logging.py` (four tests: the API server, worker and Beat subprocesses did not print their start-up line within the test's wait) and `tests/integration/test_seed.py::test_files_go_to_the_object_store_through_presigned_urls` (a `TimeoutError` in setup) failed while several suites ran at once, as 13-03 recorded for the same logging tests. This ticket touches neither logging nor the seed. Run alone they pass, and with their coverage appended to the full run's the gate is 100%.

## End-to-end (deferred)

Not run here, by instruction: the Playwright stack runs once on the integrated branch. Updated specs, which lint, typecheck and list ([e2e-list.log](e2e-list.log)):

- `frontend/e2e/tests/version-kpis.spec.ts`: pins v1 to Automatic and checks the "Searches per reply" card (0.0 mean, Retrieval Mode: Automatic, 0 Searches in 2 replies).
- `frontend/e2e/tests/version-comparison.spec.ts`: v1 Automatic, v2 Agentic (the fake chat model makes one Search per reply); checks the "Mean searches per reply" row (0.00 / 1.00 / +1.00), "Retrieval Mode: Automatic → Agentic" in the configuration changes, and the CSV line.

The integrated run must also cover, unchanged but touched by this ticket's code: `retention.spec.ts` (purge path), `agent-drafts.spec.ts` (Version list and Compare section), and `guardrail-analytics.spec.ts` (KPI cards).
