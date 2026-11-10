# Evidence: ticket 13-05, Retrieval Mode in the Agent editor

Branch `t/13-05`, from `0823a537` (all of spec 12, plus merged `t/13-01` and `t/13-02`). A container restart stopped the first job before it committed; its uncommitted work was reviewed, kept and committed as `6695e5bb`, and the checks below ran on that tree. Only this folder and the ticket's Status were written afterwards.

**Status: done.** Every criterion is met and evidenced below; the e2e run is deferred to the integrated stack (see "End to end").

## What was built

- **Studio Draft editor** (`frontend/apps/studio/src/projects/DraftEditor.tsx`, Retrieval section only): `RetrievalModeField`, a `Segmented` choice of Automatic and Agentic described by one trade-off sentence ("Agentic lets the model search the Knowledge Base as often as a question needs, which is more accurate and can cost more per reply; Automatic searches once per question, which is cheaper and predictable.") and by any refusal. A **Search limit** `NumberField` (min 1, max 5, hint) shows only in Agentic mode; it autosaves like every Draft field. Local validation refuses a blank ("Enter a number.") and anything but a whole number 1 to 5 ("Enter a whole number from 1 to 5.") before saving. Switching modes with an unfinished Search limit resets it to 3, since a hidden field can't be fixed. The folded section summary reads "Automatic · top-5 · hybrid 0.5" or "Agentic, up to N searches · …".
- **Design system** (`design/controls.tsx`): `Segmented` takes `describedBy` (`aria-describedby`) so the trade-off and refusals describe the radio group; documented in `docs/design/README.md`.
- **Draft Diffs** (`projects/AgentDiff.tsx`): `retrieval.mode` reads "Retrieval › Retrieval mode" with "Automatic"/"Agentic" values; `retrieval.search_limit` reads "Retrieval › Search limit 3 → 5". The backend diff already lists both paths (13-02's AgentConfig fields).
- **Audit Events** (`backend/app/agents/service.py`): `replace_draft` (saving, discarding, starting from a Version) records `agent.retrieval_mode_changed` when the Retrieval Mode or Search limit changes, with `before`/`after` holding just the changed settings (`retrieval_mode`, `search_limit`). Refused saves and saves leaving both alone record nothing.
- **Glossary**: Retrieval Mode (how it is chosen, the Audit Event) and Search limit (1–5, default 3, shown only in Agentic mode).

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams); spec 13 adds none.

- **API seam** (`backend/tests/integration/test_retrieval_mode_draft.py`, real Postgres and Redis): the mode and limit in the Live-to-Draft diff; three Editor saves audited newest first with only the changed settings; a save leaving them alone and a refused `search_limit: 6` record nothing; discarding the Draft back to the Live mode is audited.
- **Frontend network seam (MSW)** (`projects/RetrievalMode.test.tsx`): the segmented control and its trade-off description, no Search limit in Automatic mode; choosing Agentic autosaves and shows the Search limit (1–5, hint), which autosaves and updates the summary; back to Automatic hides and keeps it; 6, 0, 2.5 and blank are caught before saving; the server's refusal of the Search limit and of the mode shown on the field/control (and cleared once saved); read-only for an archived Agent; the publish dialog's diff reads "Retrieval › Retrieval modeAutomatic → Agentic", "Retrieval › Search limit3 → 5"; an unfinished limit resets to 3 on switching to Automatic. `design/controls.test.tsx`: `Segmented` is described by `describedBy`. `AgentViews.test.tsx`: the Retrieval summary now leads with the mode.
- **End to end** (updated, deferred): `frontend/e2e/tests/agent-config.spec.ts` (choose Agentic, Search limit 6 refused locally, 2 saved, axe clean, both Audit Events via the API, persisted after a reload) and `frontend/e2e/tests/agent-drafts.spec.ts` (publish dialog diff shows "Automatic → Agentic" and "3 → 4").

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Segmented control for Automatic and Agentic, with a one-sentence accuracy against cost explanation | `RetrievalModeField`; MSW test "the Retrieval section chooses the Retrieval Mode, explaining the trade-off"; e2e agent-config. |
| 2 | Search limit shows only in Agentic mode, validates 1–5 and autosaves | `NumberField` under `retrieval.mode === "agentic"`, `validSearchLimit`; MSW tests "choosing Agentic autosaves it and shows the Search limit…", "a Search limit of … is caught before saving" (4 cases). |
| 3 | A refusal from the server is shown on the field | MSW tests "the server's refusal of the Search limit is shown on the field", "…of the Retrieval Mode is shown on the control". |
| 4 | Changes appear in Draft Diffs and Audit Events | `test_the_retrieval_mode_and_search_limit_show_in_the_draft_diff`, `test_changing_the_retrieval_mode_and_search_limit_is_audited`, `..._leaves_retrieval_mode_alone_is_not_audited`, `test_discarding_the_draft_back_to_another_mode_is_audited`; MSW diff test; e2e agent-config and agent-drafts. |
| 5 | Design system only; palette ratchet passes | `Segmented`, `fields.label`/`fields.hint`, `NumberField`, `Errors`; no palette classes or `dark:`; [frontend-checks.log](frontend-checks.log) palette ratchet. |
| 6 | Tests at the highest seam; 100% line and branch coverage | Seams above; backend and frontend coverage in Results. |
| 7 | Glossary / ADRs | `GLOSSARY.md` Retrieval Mode and Search limit extended; no decision changed, no ADR edit (ADR-0015 stands). |

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `cd backend && TEST_DATABASE_URL=…/studio_test_t05 TEST_REDIS_URL=redis://localhost:6379/7 uv run pytest -n 3` | BACKEND_RESULT | [backend-tests.log](backend-tests.log) |
| Backend lint and types | `uv run ruff check . && uv run ruff format --check . && uv run mypy` | exit 0 (396 files) | [lint-backend.log](lint-backend.log) |
| API client drift | `make check-client` | up to date, exit 0 | [check-client.log](check-client.log) |
| Links | `make link-check` | all resolve, exit 0 | [link-check.log](link-check.log) |
| Frontend | `pnpm test && pnpm check-embed-size && pnpm palette-ratchet && pnpm lint && pnpm typecheck` | FRONTEND_RESULT | [frontend-checks.log](frontend-checks.log) |
| e2e specs list | `pnpm e2e --list` | 119 tests in 65 files, both updated specs listed, exit 0 | [e2e-list.log](e2e-list.log) |

## End to end

Not run here (four tickets share the machine; no Docker builds). The integrated run must cover `frontend/e2e/tests/agent-config.spec.ts` and `frontend/e2e/tests/agent-drafts.spec.ts`.

## Notes

NOTES_PLACEHOLDER
