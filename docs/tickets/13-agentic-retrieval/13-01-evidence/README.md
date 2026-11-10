# Evidence: ticket 13-01, Prefactor: Chunk labels assigned per reply

Branch `t/13-01`, from `6d7182e` (spec 13 reworked into nine tickets). The claim commit `d9265b3` set Status `in-progress`; the change is commit `0f07f7b`, and `5e23a6e` only reorders a sentence in the `runtime.py` module docstring (review feedback). Every check below ran at `5e23a6e`; only this folder was written afterwards.

**Status: done.** Every criterion is met and evidenced below.

## What was built

- **`GivenChunks`** (`backend/app/runtime/prompt.py`): the per-reply record of the Chunks given to the model. `give(chunks)` labels each Chunk not given before `C1`, `C2` … in the order it was first given and returns the newly labelled ones (`LabelledChunk(label, chunk)`); a Chunk given again keeps its first label and is not repeated. `labelled(label)` looks a label up.
- **`data_blocks`** takes the reply's record (a fresh one by default) and writes the Chunks block from it, so a label no longer comes from `Candidate.rank`.
- **`citations.resolve`** (`backend/app/runtime/citations.py`) resolves labels through the same record and returns `LabelledChunk`s; unknown labels are still dropped and a Chunk cited twice counts once.
- **`run_turn`** (`backend/app/runtime/runtime.py`) creates one `GivenChunks` per reply, passes it to `data_blocks` and `resolve`, and emits `CitationEvent(entry.label, entry.chunk)`. `DoneEvent.cited` still holds the Chunks.
- In Automatic mode retrieval ranks from 1 in the order the Chunks are given, so the first-given order equals the rank and nothing changes for Members or Visitors. Several Searches per reply (13-02) only need to call `give` again on the same record.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams); no human was available to confirm seams, so these are the pre-agreed ones. The behaviour has no new API surface (it is internal to one reply), so the highest seam is the runtime contract, `run_turn`, with a Pydantic AI `FunctionModel` as the chat-model fake, as in `tests/unit/test_prompt_assembly.py`.

- `backend/tests/unit/test_chunk_labels.py` (new):
  - `test_labels_follow_the_order_chunks_are_given_not_their_rank`: Chunks of rank 7 then 3 are given as `[C1] later.md` and `[C2] earlier.md`; a text answer citing `[C2]` and `[C9]` yields exactly `CitationEvent("C2", earlier)`, and `DoneEvent.cited == [earlier]`.
  - `test_a_chunk_given_twice_keeps_its_first_label`: the same Chunk given twice appears once, the second Chunk is `C2`, no `C3` exists; structured output citing `c2`, `[C1]`, `C3` resolves to C2 then C1 (normalised, unknown dropped, order first cited).

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | The runtime assigns Chunk labels from a per-reply record of Chunks given to the model, in the order they were first given | **Code:** `GivenChunks.give`, `data_blocks(..., given)`, one `GivenChunks()` per `run_turn`.<br>**Tests:** both tests in `test_chunk_labels.py` (labels follow the given order, not rank; a Chunk given again keeps its first label and is not repeated). |
| 2 | Citations (structured output and label parsing) resolve through the same record | **Code:** `citations.resolve(labels, given)` looks labels up with `given.labelled`; `run_turn` passes the reply's record.<br>**Tests:** label parsing in `test_labels_follow_the_order_chunks_are_given_not_their_rank` (text-only profile); structured output in `test_a_chunk_given_twice_keeps_its_first_label` (default profile, native JSON output). |
| 3 | Automatic mode behaves exactly as before: the existing Playground, prompt-assembly, citation and canary tests pass unchanged | `git diff 6d7182e 5e23a6e --stat` touches only `app/runtime/{citations,prompt,runtime}.py`, the new `tests/unit/test_chunk_labels.py`, the ticket file and this evidence folder: no existing test changed. The whole suite, including `test_playground.py`, `test_prompt_assembly.py`, `test_citations_trace.py` and `test_canary.py`, passes: [backend-tests.log](backend-tests.log). |
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams above. Backend gate: **100.00%** lines and branches (11999 statements, 1464 branches), [backend-tests.log](backend-tests.log). |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | No new domain term: `GLOSSARY.md` already defines **Chunk label** as numbered "in the order the reply's Searches first found them, so a Chunk found twice keeps its first label" (added with spec 13), which this ticket now implements; `GivenChunks` is a code name, not a domain term. No ADR decision changed. |

## Results

All local. Postgres (pgvector), Redis and RustFS are the `docker-compose.yml` services started with `make services` (all healthy).

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `TEST_WORKERS=auto make test-backend` (4 xdist workers) | **2547 passed**, 0 failed, 0 skipped in 33 min 23 s; coverage 100.00%; exit 0 | [backend-tests.log](backend-tests.log) |
| Lint and type-check | `make lint-backend` (ruff check, ruff format --check, mypy --strict) | exit 0 (393 files) | [lint.log](lint.log) |

## Notes and gaps

- An earlier run of this branch, before the compose services were up, had 14 tests fail or error, all of them needing RustFS on `localhost:9000` (no RustFS was running), with coverage 99.70%. With RustFS up all of them pass; no code or test was changed for it.
- In that earlier run three `test_logging` tests timed out under parallel load and passed when run alone. In this run they passed on the workers too; no test was weakened.
- Backend-only ticket: no frontend, API client, migration or e2e change, so those checks were not re-run.
