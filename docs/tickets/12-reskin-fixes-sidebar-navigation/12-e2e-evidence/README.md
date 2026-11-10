# Spec 12: the compose-stack end-to-end suite

Every spec-12 ticket (12-01 to 12-11) listed "no compose stack" as a gap: the Playwright `studio` project was listed and type-checked, not run against the stack. This run closes that gap for the whole spec, on the integration branch `claude/gallant-euler-zxqfxb` after all 11 tickets merged (`e1020011`), with the fixes below.

## Result

**118 passed, 0 failed, 0 skipped, 0 flaky** (both Playwright projects, `harness` and `studio`; no retries: `CI` unset, as `make e2e` runs it). Log: [e2e.log](e2e.log).

Frontend checks at the same tree: `make lint-frontend && make test-frontend` exit 0: ESLint, `tsc`, 84 Vitest files / 1086 tests at 100% coverage, the embed size budget and the palette ratchet (0 uses). Log: [frontend-checks.log](frontend-checks.log).

## Command

`make e2e`'s three steps (`compose up --wait`, `make seed`, `pnpm e2e`), with the stack built from this worktree:

```sh
docs/tickets/12-reskin-fixes-sidebar-navigation/12-e2e-evidence/build.sh "$PWD" 12e2e      # make images, plus the sandbox proxy CA, minus the apt upgrade
C="docker compose -p rag12e2e -f docker-compose.yml -f docs/tickets/12-reskin-fixes-sidebar-navigation/12-e2e-evidence/compose.e2e.yml"
$C up -d --no-build --wait
make seed COMPOSE="$C"                        # make seed-reset before a rerun
cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm e2e --trace off
```

Sandbox-only differences from `make e2e`, and why:

- [build.sh](build.sh) builds the committed Dockerfiles with the agent proxy's CA added to each stage and the `apt-get upgrade` step left out (the proxy refuses plain-HTTP apt), as 12-08 did. `WITH_PDF=false` (disk); **`BUNDLE_MODELS=true`**, so the real local Embedding Model and the ONNX classifiers run, unlike 12-08's light stack (no heuristic overrides, so `documents` and `playground` see the bundled classifier's wording).
- [compose.e2e.yml](compose.e2e.yml) runs the stack as its own compose project, `rag12e2e`, using those images, with its Postgres, Redis and RustFS unpublished: the shared `rag-agent-studio` Postgres, Redis and RustFS (used by 13-01's backend suite) hold 5432, 6379 and 9000/9001 and were not touched. Every other port is the default, so no `E2E_*` URL overrides are needed.
- Docker Hub answered some image-metadata requests with 429 Too Many Requests; the rebuilds were retried until they went through.

## Failures and fixes

Run 1 ([e2e-run1-cut-off.log](e2e-run1-cut-off.log)) was cut off by the harness's 10-minute limit after 96 of 118 tests: 14 failed. Run 2 ([e2e-run2-4-failed.log](e2e-run2-4-failed.log)), after the first fixes, ran to the end: 114 passed, 4 failed (the 22 tests run 1 never reached). Each failure was reproduced on its own against the stack, fixed, and rerun green before the final full run.

### App bugs (fixed in the Studio, each with a unit test that failed first)

| Spec | Symptom | Cause | Fix |
| --- | --- | --- | --- |
| `instructions-versions` | After publishing v2, Compare said "1 added, 1 removed" from v1, not "No differences: v2 and the Draft" | `CompareInstructions` seeded its From side with `useState(currentId)`, so it kept the Current Version of its first render (v1) after a publish moved it | `InstructionsVersions.tsx`: From follows the Current Version until the Member picks a side. Test: the publish test checks Compare follows v3 |
| `embed` | axe `label-content-name-mismatch` (WCAG 2.5.3) on the Copy button right after copying | `CodeBlock`'s button was always named "Copy Embed Snippet" while it showed "Copied" | `CodeBlock.tsx`: the name starts with what it shows ("Copied Embed Snippet"). `CodeBlock.test.tsx` and the spec use the new name |
| `accessibility` | Two `h1`s on the Document viewer (strict-mode violation) | The converted markdown rendered the Document's `# Title` as an `h1`, under the page's `h1`, the Document's `h2` and the section's `h3` | `DocumentViewer.tsx`: the Document's headings render three levels down (h1→h4, h2→h5, the rest h6), looking as before. `DocumentViewer.test.tsx` checks the levels |
| `tags` | Timed out: Manage tags stayed open after Escape, so the next row action never got through | The duplicate-name submit disables the focused Add Tag button, focus drops to the page, and `Dialog` only heard Escape inside its panel | `Dialog.tsx`: Escape also closes the top dialog when focus has fallen out of it (only the top one of stacked dialogs). Two new `Dialog.test.tsx` tests |

### Specs behind the spec-12 changes (fixed in the spec)

| Spec(s) | Cause | Fix |
| --- | --- | --- |
| `auth`, `mfa`, `password-reset`, `require-mfa`, `members`, `projects`, `invites`, `credentials`, `organisation-switcher` | 12-03's empty state adds an `h2` "No Projects yet", so `heading "Projects"` matched two | The Projects page heading is looked for at level 1 |
| `projects` | The empty state's "No Documents yet" `h2` matched `heading level 2 "Documents"` | `exact: true` |
| `invites` | 12-05's invite dialog closes after each invite; the second invite filled a form that was gone | Reopen "Invite someone" before the second invite |
| `select-chevron` | 12-01's spec predates 12-05: the invite's Role select is in the dialog | Open the dialog first |
| `agent-config` | Experience and Guardrails are folded (11-08) again after the reload | Open them again before checking their values |
| `rate-limits` | The Playground is its own Agent view (11-08); the spec stayed on Embed & limits | `openAgentView(page, "Playground")` |
| `document-editions` | While edition 2 processes, the old edition's row (Ready) also names `handbook-2027.md`, so "Ready" matched too early | Wait for "New edition 2" to go, then check Ready |
| `version-comparison` | The design-system Diff is a table of lines, not a list | Look for the table |
| `version-kpis` | `getByLabel("Agent")` also matched the "Loading the Agents" status while the page loaded | `getByRole("combobox", { name: "Agent" })`, as `five-minute-demo` does |

### Not a code fault

- `password-reset` failed once in run 1 with the machine's load near 10 on 4 CPUs (other sessions building); it passed when rerun on its own and in runs 2 and 3, with no change.

No test was skipped, disabled, quarantined or given a longer timeout.
