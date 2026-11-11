# Evidence: ticket 10-06, README and automated demo

Branch `ticket/10-06-readme-demo`, from `origin/candidate` at `0b77e0c` (#78, 07-07). The claim commit `6b14c58`, the first on the branch, set Status `in-progress`. The feature is three commits: README, link check and demo spec (`a7bbc41`), the 10-05 merge with the README's seed step (`b1a4d92`), and the 07-08 merge with the Organisation cost step (`c65d6fc`). The other commits change only this folder and the ticket file. This ticket adds no migration (candidate's head is still `0039_retention_tombstones`).

**Status: done.** Every criterion is met and evidenced below. Gaps and best guesses are at the end.

## What was built

- **`README.md`** (new; replaces the short one 10-05 added, keeping its seed steps): CI badges for every workflow and a coverage badge; the two-sentence pitch and a screenshot of the widget on the shop page; what the product does; the **five-minute demo** script (eleven timed steps in the spec's order, with the demo Owner and Editor credentials); the quickstart; a Mermaid architecture diagram with the request and ingestion paths; the stack; testing (coverage gate, seams, e2e, the Attack evaluation suite, infra and links) and security (envelope encryption, auth, layered injection defence, embed protections) sections; deploy, **seed** and destroy for the AWS demo with the expected cost; links to `GLOSSARY.md`, every ADR, `docs/plan.md`, `docs/specs`, `docs/tickets`, `docs/development.md` and the seed licence.
- **The link check**: `scripts/ci/links.mjs` (no dependencies, offline) finds every link in the Markdown git tracks (inline links and images, reference definitions; not footnotes, not code spans or fences), skips external ones (any URL scheme or `//host`), and checks that the file or folder exists (relative to the linking file, or the repository root for `/…`) and that a `#anchor` names a heading (GitHub's slug rules, duplicate headings `-1`, `-2`) or an `<a id|name>` in the target Markdown file. `scripts/ci/link-check.mjs` is the command line. `make link-check` runs the checker's tests with Node's 100% line, branch and function thresholds, then the check. **`.github/workflows/links.yml`** runs `make link-check` on every push and pull request.
- **The five-minute demo as one Playwright test**: `frontend/e2e/tests/five-minute-demo.spec.ts`, one `test("the five-minute demo")` with a `test.step` per README step, against the seeded compose stack: (1) the demo Owner signs in to the Northwind Handbook Project; (2) the Document viewer shows the handbook's flagged Chunk; (3) a Playground answer from the HR helper and its Trace; (4) the HR helper's Live History: published v1 → v2, reverted v2 → v1, published v1 → v3; (5) the analytics comparison: thumbs-up rate v2 < v1 < v3, v3 marked low confidence; (6) a Visitor chats with the Product FAQ on the shop page; (7) the disallowed origin's frame is refused; (8) each attack-panel button and the layer outcome it expects; (9) the Token Budget spent: the widget's unavailable text and the Studio's "Budget exhausted"; (10) the Organisation cost page by Project and by Agent; (11) the Audit tab filtered to `agent.reverted`, `agent.bulk_published` and `project.instructions_published`. axe (WCAG 2.2 AA) runs on the Studio pages along the way.
- **Docs**: `GLOSSARY.md` (new **Five-minute demo**), `docs/development.md` (`make link-check`, `links.yml`, and `make e2e` now described as seeding and running the demo).

## Test seams

From the [shared test seams](../../../specs/README.md#shared-test-seams) and spec 10's Testing Decisions ("End-to-end: after `make seed`, Playwright … This is the 'five-minute demo' automated"; "README links: a CI job checks that every relative link in the README and docs resolves"). Not confirmed with a human (none available); they are the seams the spec names.

- **End-to-end seam:** `five-minute-demo.spec.ts` (Playwright, Chromium) against the compose stack after `make seed`, with the real local ONNX classifier and the demo provider.
- **Link checker seam:** its module interface (`checkLinks`, `main`, `gitMarkdownFiles`, `slugify`) over temporary repositories: `scripts/ci/tests/links.test.mjs` (8 tests, 100% line/branch/function coverage). Written test first: the suite failed before `links.mjs` existed, and two later cases (headings with code spans, footnotes) were added red, then fixed.
- No backend or Studio code changed, so the backend and frontend suites and their coverage gates are run unchanged.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | The README has the pitch, a Mermaid architecture diagram, the stack, a quickstart, testing and security sections, deploy and destroy instructions with cost, and links to the glossary, ADRs, plan, specs and tickets | [`README.md`](../../../../README.md): the pitch under the badges; sections [Architecture](../../../../README.md#architecture) (a `mermaid` flowchart), [Stack](../../../../README.md#stack), [Quickstart](../../../../README.md#quickstart), [Testing](../../../../README.md#testing), [Security](../../../../README.md#security), [Deploy and destroy (AWS demo)](../../../../README.md#deploy-and-destroy-aws-demo) (bootstrap, deploy, seed, destroy, and the expected cost from `docs/deploy-demo.md`: about 0.33 USD an hour, 8 USD a day, 240 USD a month always on, about 1 USD a month after destroy) and [Documentation](../../../../README.md#documentation) (glossary, each ADR, plan, specs, tickets). Every one of these links is checked by the link check (criterion 3). |
| 2 | The five-minute demo script is in the README, with CI and coverage badges | [Five-minute walkthrough](../../../demo.md#five-minute-walkthrough) (moved from the README to `docs/demo.md` later): eleven timed steps in the spec's order (Studio, flagged Chunk, Agent editor and Trace, publish and revert, shop embed, disallowed origin, attack panel, Token Budget, analytics comparison, Organisation cost, Audit tab) with the sign-in details. Badges: GitHub Actions status badges for `backend`, `frontend`, `e2e`, `infra`, `security` and `links` (each linking to its workflow), and a coverage badge "100% line + branch (gated)" linking to the backend workflow. GitHub Actions is down, so the status badges can't be shown green (see Gaps). |
| 3 | A link-check CI job verifies every relative link | `.github/workflows/links.yml` → `make link-check`. Locally: the checker's 8 tests pass at 100% coverage and **"Checked 1919 relative links in 199 Markdown files: all resolve."** ([remerge-link-check.log](remerge-link-check.log); 1899 in 198 files at the final gate, [link-check.log](link-check.log)). Checked by hand that it fails on a broken README anchor (`#five-minute-demox` → "README.md:15 #five-minute-demox (no heading or anchor named five-minute-demox)", exit 1). The workflow itself could not run (Actions down). |
| 4 | The whole demo runs as one Playwright test | `five-minute-demo.spec.ts` "the five-minute demo": **passed** in the full e2e run at the final gate (`60c61c8`, 16.8–18.5 s; [e2e.log](e2e.log), test 37) and again after the last re-merge with the Organisation cost step (`7e079ac`, [remerge-e2e.log](remerge-e2e.log), test 37). `make e2e` runs it after `make seed` (as in CI's `e2e.yml`). |
| 5 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams as above. Link checker 100% line/branch/function ([link-check.log](link-check.log)). Backend 100.00% (11778 statements, 1442 branches; [backend-tests.log](backend-tests.log)); frontend 100% statements and branches ([frontend-tests.log](frontend-tests.log), [remerge-frontend-tests.log](remerge-frontend-tests.log)). |
| 6 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: new **Five-minute demo** (with _Avoid_). No decision changed (the README documents existing decisions; the link check is the spec's CI job), so no ADR edit. |

## Results

All runs are local and one at a time (GitHub Actions is down; the user authorised merging on local results), in the ticket's worktree with a clean tree (each log's first line names its command, commit and checkout). [run-checks.sh](run-checks.sh) runs install, lint, client drift, frontend, the link check, the backend suite (`TEST_WORKERS=3`, fresh `rag1006-pg/redis/rustfs` containers) and security; [run-e2e.sh](run-e2e.sh) builds the images ([build.sh](build.sh)) and runs every e2e spec in compose project `rag1006-e2e` ([compose.sandbox.yml](compose.sandbox.yml), [e2e.env](e2e.env)). Images, containers and volumes were removed afterwards.

**Final gate, after re-merging `origin/candidate` at `3139e62`** (#77, 10-05; merge `b1a4d92`, one conflict in `README.md`, resolved by keeping this ticket's README and adding 10-05's seed workflow to its deploy section), at `60c61c8`:

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `make install` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint` (ruff, ruff format, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | exit 0, up to date | [client-drift.log](client-drift.log) |
| Frontend tests + coverage + loader budget | `make test-frontend` | exit 0: 59 files, **804 tests**; 100% statements (3894/3894) and branches (2599/2599); `embed.js` 778 B gzipped | [frontend-tests.log](frontend-tests.log) |
| Link check | `make link-check` | exit 0: 8 tests, 100% coverage; 1899 links in 198 files resolve | [link-check.log](link-check.log) |
| Backend tests + coverage (the full run) | `TEST_WORKERS=3 make test-backend` | exit 0: **2498 passed**, coverage 100.00% | [backend-tests.log](backend-tests.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` | exit 0 both: no leaks; no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | exit 0 | [images.log](images.log) |
| End-to-end (the full run) | stack up, `make seed`, `pnpm e2e tests/` (CI settings) | exit 0: **90 passed**, none flaky, the five-minute demo among them | [e2e.log](e2e.log) |

**After the last re-merge** (`origin/candidate` at `a76f8b1`, #79 07-08 Organisation cost, merged while the gate above ran; a clean merge, `441158a`; `c65d6fc` adds the Cost step to the README and the demo). 07-08's own branch had passed its full gates on a tree with 10-05 merged, and this ticket changes no backend or Studio code, so the backend suite was not repeated in full; [remerge-checks.sh](remerge-checks.sh) ran, at `7e079ac`:

| Check | Result | Log |
|---|---|---|
| `make lint` | exit 0 | [remerge-lint.log](remerge-lint.log) |
| `make check-client` | exit 0 | [remerge-client-drift.log](remerge-client-drift.log) |
| `make link-check` | exit 0: 1919 links in 199 files | [remerge-link-check.log](remerge-link-check.log) |
| `make test-frontend` | exit 0: **810 tests**, 100% statements (3926/3926) and branches (2637/2637) | [remerge-frontend-tests.log](remerge-frontend-tests.log) |
| Backend modules the merge touched or that the demo relies on: `test_organisation_cost.py`, `test_openapi.py`, `test_tenant_isolation.py`, `test_seed.py`, `test_seeded_history.py` | exit 0: **745 passed** | [remerge-backend-merged.log](remerge-backend-merged.log) |
| Images | exit 0 | [remerge-images.log](remerge-images.log) |
| **Every e2e spec** again | exit 0: **91 passed**, the five-minute demo (with its Cost step) and 07-08's `organisation-cost.spec.ts` among them | [remerge-e2e.log](remerge-e2e.log) |

**Backend full run on the final tree** (because the 07-08 re-merge brought shared backend code, `main.py`'s router list): `TEST_WORKERS=3 make test-backend` at `e304736` (`origin/candidate` `a76f8b1` merged, clean tree, fresh `rag1006-pg/redis/rustfs` containers, removed afterwards): exit 0, **2516 passed** in 34 min, coverage 100.00% ([final-backend-tests.log](final-backend-tests.log)). `origin/candidate` had not moved when this finished; this ticket adds no migration (the migration chain ends at `0039`, as on candidate).

An earlier full backend run, before the 10-05 merge (`8b42e71`), had 2493 passed and 1 failed: `test_logging.py::test_the_worker_writes_only_json_lines` didn't see its worker's start-up line in time under the shared machine's load (load average 12–14). It passed on rerun (8 passed) with no change: [run1-backend-tests.log](run1-backend-tests.log), [run1-backend-rerun.log](run1-backend-rerun.log). The seed's JSON request logs were filtered out of the committed e2e logs (lines starting `{"`), nothing else.

## Gaps and best guesses

- **GitHub Actions is down**, so the badges point at the workflows but can't show green, and the new `links.yml` job has not run on GitHub; it runs `make link-check`, which passes locally. There is no hosted coverage service: the coverage badge is a static shields.io badge stating the enforced gate (100% line and branch, ADR-0008), linked to the backend workflow whose run enforces it. **Best guess** recorded instead of asking: a static gate badge over adding a third-party coverage service (no external accounts or paid services).
- **The link check is offline by design**: it verifies relative links and anchors only, as the criterion asks; external URLs are not fetched (no network in CI needed, no flakiness from third-party sites).
- **The analytics comparison** asserts the ordering (v2 < v1 < v3) and v3's low-confidence mark rather than exact percentages: the seed is deterministic, but ordering is the story the demo tells and survives tuning of the seed's probabilities. 07-05 (side-by-side Version comparison) is not on candidate, so the demo compares Versions by switching the Analytics tab's Version select; if 07-05 merges later, the README's step 9 and the demo test should move to it.
- **The Token Budget step spends the Low-budget helper's budget for the day**; `demo-pages.spec.ts` asserts the same end state and the page's starting status is the static budget, so the two specs pass in any order (both did in the full runs).
- **Deploy and destroy** are documented from the 09-xx Terraform and 10-05's seed workflow; nothing was applied to AWS (no credentials), and the cost figures are `docs/deploy-demo.md`'s estimates.
- **Sandbox limits** (as in earlier tickets): images built with `WITH_PDF=false BUNDLE_MODELS=true` (build.sh adds only the egress proxy CA and the `seed` build context); the e2e stack runs `EMBEDDER=fake` with the real local input classifier and the demo provider (no real key or paid call); host ports moved by compose.sandbox.yml and e2e.env. `make infra-check`, the live suite and the Trivy scan were not run (no infrastructure or image changes in this ticket).
