# Evidence: ticket 04-02, Markdown editor

Branch `ticket/04-02-markdown-editor`, from `origin/candidate` at `7a89f6e` (04-01, the blocker, merged). The claim commit, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope this ticket leaves to later tickets on purpose, plus what this sandbox can't run.

## What was built

- **Shared UI package** (`frontend/packages/ui`): `MarkdownEditor`, a TipTap 3 editor (`@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/markdown`, all pinned at `3.32.0`, released 2026-10-13; `marked@17.0.6`). It shows markdown formatted, with a toolbar (Bold, Italic, Inline code, Heading, Bulleted list, Numbered list, Code block) and a **Markdown** view that edits the text itself. Props: `label`, `defaultValue`, `onChange`, `name` (submits with a form through a hidden input), `maxLength`, `disabled`.
  - **`disabled` is live.** Archiving or restoring a Project while its Instructions tab is open locks or unlocks the editor in place: `editor.setEditable` follows the prop in the formatted view, and the Markdown view's textarea is `disabled` with it. If the Project is archived while the Markdown view is open, that view stays open for reading but can't be typed into; the Markdown toggle comes back when the Project is restored.
  - **`maxLength` in both views.** The Markdown view refuses keystrokes past the limit. The formatted view can't refuse them without rewriting the text, so a count (`n / 20000 characters`) sits under the editor. Past the limit it reads `…: k too many`, turns red, and the textbox gets `aria-invalid` and `aria-describedby` pointing at the count. The server's 422 still guards the save.
  - **Kept exactly until edited.** Loading never calls `onChange` and never rewrites the value.
  - **Written back exactly.** The editor's dialect is CommonMark without raw HTML or bare-URL autolinks. Prompts are text for a model, so `<context>`, `&` and URLs stay literal. TipTap's own writer escapes every `_`, `[` and `~` and turns `<` and `&` into HTML entities. The editor replaces that: text is written as typed unless it would read back as formatting, and only then escaped. Trailing whitespace is kept.
  - **Markdown view:** it opens on the stored text exactly, not on the editor's rewrite of it, so text loaded in a spelling the editor would normalise (`*` bullets, `__bold__`) keeps it when edited there. Text typed there is stored exactly as typed. Switching back shows it formatted and isn't an edit.
  - **Soft breaks survive edits.** Typing in a paragraph makes ProseMirror read that paragraph back from the page, and by default it turns a newline in the text into a hard break (`  \n`). Paragraphs are `whitespace: "pre"` (`@tiptap/extension-paragraph`, `3.32.0`), so a soft break stays a soft break.
- **Project Instructions** (backend): one markdown Draft per Project.
  - The column is `projects.instructions` (migration `0018_project_instructions`, after 04-06's `0017_message_retrievals`, `text NOT NULL DEFAULT ''`).
  - `getProjectInstructions` (GET) and `saveProjectInstructions` (PUT `…/projects/{id}/instructions`, body `{markdown}`, up to 20,000 characters like the system prompt) are open to Editors and Owners. An archived Project is read-only (409).
  - A save that changes the text records `project.instructions_updated` with the before and after text.
  - The Playground now passes the Project's Instructions to `run_turn`. 04-01 passed `""`.
- **Studio:**
  - The Agent's system prompt uses `MarkdownEditor`: in 04-07's full Draft editor (`DraftEditor.tsx`, Behaviour group), it is stored as markdown and autosaved with the rest of the Draft.
  - The Project page's Instructions tab, a placeholder before this ticket, now holds the Instructions editor with **Save Instructions**. It is read-only on an archived Project.
  - The Studio's Tailwind build also scans `packages/ui/src` (`@source` in `index.css`).
- **Generated API client** regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams).

- **API seam:**
  - `backend/tests/integration/test_project_instructions.py` runs the app in process against real Postgres and Redis.
  - `test_playground.py::test_the_project_instructions_reach_the_model_before_the_system_prompt` uses the echoing `FunctionModel`.
  - `test_openapi.py` lists the two new operations.
- **Network seam (Testing Library + MSW):**
  - `packages/ui/src/MarkdownEditor.test.tsx` tests the shared component through what a person sees and does: the textbox, the toolbar and the Markdown view.
  - `apps/studio/src/projects/InstructionsTab.test.tsx` and the updated `AgentPage.test.tsx` and `AgentsTab.test.tsx` test the Studio, with `fakeProjectsApi` serving the Instructions.
  - jsdom can't measure text. `test/setup.ts` stubs `getClientRects`, `getBoundingClientRect` and `elementFromPoint` with empty answers so ProseMirror can scroll the selection into view.
- **End-to-end seam:**
  - `frontend/e2e/tests/instructions.spec.ts` drives the real editor in Chromium, with axe.
  - `playground.spec.ts` was updated for the editor.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | A TipTap-based editor in the shared UI package stores markdown | **Code:** `frontend/packages/ui/src/MarkdownEditor.tsx`, exported from `@studio/ui`. `onUpdate` emits `editor.getMarkdown()`, never HTML.<br>**Tests** (`MarkdownEditor.test.tsx`):<br>• `formatting from the toolbar is stored as markdown`: Heading → `## Rules`, the lists → `- Rules` and `1. Rules`, Code block → a fenced block, Bold and Italic → `**Rules**` and `***Rules***`, Inline code → `` `Rules` ``. The buttons show `aria-pressed`.<br>• `loading markdown changes nothing until it is edited`<br>• `text typed in the Markdown view is stored exactly and shown formatted`<br>• `a rich edit keeps the trailing newline the markdown had`<br>• `a disabled editor can't be changed`<br>• `an editor follows its disabled prop after it is created` (rerendered disabled, then enabled)<br>• `the Markdown view follows its disabled prop after it is opened` (the textarea is disabled, then enabled again)<br>• `the character count shows how far the markdown is from the limit`, `no character count without a limit`<br>• `the rich editor shows the markdown formatted`<br>**E2E:** `instructions.spec.ts` types in the real editor with the toolbar. The API then holds `## House rules\n\n- Answer in **British English**. Use <context> & snake_case.` |
| 2 | A fixture table of headings, lists, code, links and emphasis round-trips exactly | `MarkdownEditor.test.tsx`, `ROUND_TRIPS`: 21 fixtures. Each is loaded into the rich editor, a character is typed and deleted, and the markdown the editor then writes (`onChange`) must equal the fixture character for character. The edit forces a real serialisation and a read of the edited paragraph back from the page. They cover:<br>• headings 1, 2 and 6; paragraphs and soft breaks; a hard break;<br>• bulleted, numbered and nested lists;<br>• inline code, and fenced code with and without a language;<br>• a link, and a link with a title;<br>• bold, italic and both; a blockquote; a rule; escaped characters;<br>• prompt tags with `&`, `{{template}}` variables, `snake_case`, `[x]`, `<` and `>`;<br>• table-like and task-like text, a bare URL, a trailing newline, and a soft break inside the paragraph being edited.<br>Empty text has its own test (`an empty editor stores nothing until something is typed`), because deleting the only character can't be simulated in jsdom.<br>A second table, `NORMALISED`, asserts, after the same edit, the forms that have more than one spelling and are written in a canonical one: `*` bullets, `__`/`_` emphasis, `1)`, Setext headings, indented code, a list straight after a paragraph, and HTML entities. Loading such text doesn't change it; only an edit in the formatted view writes the canonical form (`loading markdown changes nothing until it is edited`, `the Markdown view opens on the stored text, not the editor's rewrite of it`, and in the Studio `saving untouched Instructions sends them back unchanged`). |
| 3 | The editor is used for the Agent system prompt and the Project Instructions (one Draft field per Project, passed to the runtime) | **System prompt:** `DraftEditor.tsx` (04-07's full Draft editor, merged from candidate) uses `MarkdownEditor label="System prompt"` with `onChange` feeding the autosaved Draft; field errors from the API show under it. `AgentPage.test.tsx` and `DraftEditor.test.tsx` check the formatted display; `an Editor sets every Behaviour, Experience and Guardrails setting` types `# Role{enter}{enter}Be brief.` in the Markdown view and the autosave sends `# Role\n\nBe brief.` exactly. `playground.spec.ts` types in the real editor end to end and waits for the autosave.<br>**Project Instructions:**<br>• One Draft field: `projects.instructions` plus the GET and PUT API. Tests: `test_a_new_projects_instructions_are_empty`, `test_an_editor_saves_the_instructions_and_they_read_back_exactly`, `test_instructions_can_be_cleared`, `test_invalid_instructions_are_refused` (over 20,000 characters, missing, not a string), `test_an_archived_projects_instructions_are_read_only` and `test_instructions_are_not_found_outside_their_organisation`.<br>• Passed to the runtime: `app/playground/service.py` passes `prepared.project.instructions` to `run_turn`. `test_the_project_instructions_reach_the_model_before_the_system_prompt` asserts the model receives the preamble, then the Instructions exactly, then the system prompt.<br>• Studio: `InstructionsTab.tsx`. Its tests are `InstructionsTab.test.tsx`, with 9 tests: formatted display, an edit saved exactly (`Use <context> & cite [C1]. Answer in snake_case\n`), untouched text saved unchanged, an empty start, 422 and 409 messages, progress and a generic failure, read-only when archived, and a load failure.<br>• E2E: `instructions.spec.ts`. It also archives the Project with the tab open (the editor becomes `contenteditable=false` and Save Instructions goes), restores it (editable again) and types in it. |
| 4 | Instructions edits are recorded as Audit Events | `app/projects/service.py::save_instructions` records `project.instructions_updated` (target `project`, `before`/`after` `{instructions}`) in the same transaction, only when the text changes.<br>• `test_instructions_edits_are_recorded_as_audit_events`: two edits make two events with the right before and after, actor and target. A third save of the same text records nothing.<br>• E2E: `instructions.spec.ts` reads the event back from the Audit API. |
| 5 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are above. The coverage gates are in the results below: backend `fail_under = 100` with branches, and frontend Vitest at 100% lines, branches, functions and statements. |
| 6 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` adds **Markdown editor** (under Agents and versioning), and **Project Instructions** now says it is markdown placed after the platform preamble and before the system prompt, with one Draft per Project. No ADR decision changed. The ADR-0008 coverage gate holds, and no exclusions were added. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). Every check ran at `275ae1b`: the merge of `origin/candidate` at `05e1a18` (04-06, Citations and Trace drawer) into the branch. Candidate moved three times during this round, and each merge was taken: `17d40e4` brought in 04-07 (the full AgentConfig editor; see AC3), `c42046f` brought in 03-08 (OCR toggle) and `275ae1b` brought in 04-06. 03-08 and 04-06 each added a migration, so the Instructions migration is now `0018_project_instructions`, revising `0017_message_retrievals` (one Alembic head; `test_migrations` round-trips it). 04-06 also changed the Playground and runtime; the Project Instructions still reach `run_turn` and the prompt order test still passes. Before it, `ba5014f` fixed the second review's point: the Markdown view's textarea now follows `disabled` too, with the test `the Markdown view follows its disabled prop after it is opened`. The first review's fixes are in `0c41e72`: `disabled` is live, the Markdown view opens on the stored text, the formatted view shows the character count, and soft breaks are kept on edit. The next commit changes only this folder. Every log's first line names the commit it ran at.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against the `rag0402-*` Postgres/pgvector, Redis and RustFS containers | **1236 passed**, 7 deselected (live); coverage **100.00%** lines and branches (5992 statements, 590 branches) | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **37 files, 426 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit, covering the new TipTap and marked packages) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0402`), on images built from the merged tree | **50 passed** on the first run, including `instructions.spec.ts` (types with the toolbar, archives and restores the Project with the tab open, reads the Audit Event), `playground.spec.ts` (types the system prompt in the markdown editor and waits for the autosave) and 04-07's `agent-config.spec.ts`, each with axe scans. Earlier in this round, at `17d40e4` and `c42046f`, runs hit another ticket's `tags.spec.ts` flake under load (a new Tag not visible within 5 s; 04-07's evidence records the same) and a host-port clash with another stack; those trees were superseded by the later merges, so only this run's log is kept. Earlier rounds: an axe `label-content-name-mismatch` on the toolbar and a missing `goto` were fixed in `12655aa`. | [e2e.log](e2e.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

The last lines of `backend-tests.log` are telemetry spans the console exporter flushes at exit, from the fake model transports. They are not real provider calls.

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Project Instructions Versions, the Current Version, publish and revert (05-01). The migration there turns `projects.instructions` into the Draft plus a v1.
  - Picking an Instructions Version in the Playground (05-06).
  - Autosave and the "unpublished changes" indicator, for both the system prompt and Instructions (04-07 for the Agent editor; 05-04 for Draft management). Instructions use an explicit **Save Instructions** for now.
  - 04-07 merged first and replaced the Agent page's Draft form with its full editor, where the system prompt was a plain textarea. The merge (`17d40e4`) resolves the overlap: `AgentPage.tsx`, its test and `playground.spec.ts` take 04-07's version, and `DraftEditor.tsx`'s system prompt becomes the `MarkdownEditor`.
- **Best guesses, recorded instead of asking:**
  - **The character limit in the formatted view is shown, not enforced.** Refusing a keystroke there would mean measuring the serialised markdown on every transaction and dropping edits mid-word; a visible count with `aria-invalid` tells the person before the server's 422 does.
  - "Round-trips exactly" is read as follows. The fixture table of headings, lists, code, links and emphasis, plus prompt-specific text, is written back character for character. Text is never rewritten until it is edited. Equivalent spellings (`*` bullets, `__bold__`, Setext headings and so on) are written in one canonical form once edited, as `NORMALISED` documents. A WYSIWYG model can't keep two spellings of the same structure apart. Anyone who needs a spelling kept can edit in the Markdown view, where text is stored exactly as typed.
  - **No raw HTML, autolinks or GFM extras.** Prompts often use XML-style tags and `&`. As HTML they would be dropped or entity-encoded, which changes what the model reads. Tables, task lists and strikethrough have no formatted view here, so they stay as typed text.
  - **Audit only on change.** Saving identical Instructions records no Audit Event, so a repeated save (and the later autosave) doesn't flood the log.
  - **Who can edit.** Instructions follow the same role rule as Agents: Editors and Owners, through the one policy dependency.
  - **The test seams were not confirmed with a human.** The tests use the seams the spec's Testing Decisions name: the API seam, and the network seam with "a table of markdown fixtures".
- **Sandbox limits** (as in 04-01 and 04-03):
  - The images are built with `WITH_PDF=false BUNDLE_MODELS=false`, and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here.
  - The live suite and the Trivy image scan were not run.
  - New npm dependencies (TipTap, marked) are covered by `pnpm audit` above.
