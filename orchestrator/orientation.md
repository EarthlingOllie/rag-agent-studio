# Orientation: rag-agent-studio @ origin/candidate

Surveyed 2026-11-05. Repo: github.com/EarthlingOllie/rag-agent-studio. Read-only survey; throwaway worktree at SCRATCH/wt (detached at origin/candidate).

## Branches
- `origin/candidate` exists, HEAD `e68d265` "Link specs index to tickets". Identical to `origin/main`, `claude/rag-agent-studio-wnl48h`, `claude/vibrant-goodall-lg5ka4`.
- `claude/stoic-brown-2sup3y` (d73b554) is an ancestor of candidate (0 ahead).
- `claude/hopeful-wozniak-u0p9rf` (4babb01) is 1 commit ahead: "WIP: draft spec 01 tickets (unreviewed, paused mid-run)", touching only docs/tickets/README.md. Superseded by candidate's tickets; ignore.
- GitHub: 0 PRs (any state), 0 issues. No claims recorded on GitHub.

## Repo contents (docs only, no code yet)
- `GLOSSARY.md`, `LICENSE`, `docs/plan.md` (build plan, 10 slices), `docs/adr/0001..0011`, `docs/specs/` (10 specs + README with shared test seams), `docs/tickets/` (78 tickets + README index), `.claude/skills/` (domain-modeling, grilling, grill-with-docs).
- No CLAUDE.md, no AGENTS.md, no Makefile, no package manifests (no pyproject.toml / package.json), no CI workflows, no backend/frontend/infra folders.

## Ticket conventions
- ID `<spec>-<NN>`; file `docs/tickets/<NN-spec-slug>/<NN-ticket-slug>.md`. Index with titles and blockers: `docs/tickets/README.md`.
- Each ticket header: `**Ticket:** \`<id>\` · **Spec:** link`, then "What to build", `**Blocked by:**` (ticket IDs, may cross specs), `**Status:** <value>`, then a `- [ ]` acceptance checklist (always ends with: tests at highest seam with 100% line+branch coverage; glossary/ADR updates).
- Status: all 78 tickets currently `**Status:** ready-for-agent`. No other status values are defined anywhere in the repo.
- Claim/done: NOT defined in the repo. There is no claim field, owner/assignee field, "in-progress" or "done" status value, and no GitHub issues/PRs. README only says "Work the frontier: any ticket whose blockers are all done." Implied convention (inference, not documented): done = Status line changed from `ready-for-agent` to `done` with all checkboxes ticked; a claim would need an added field (e.g. `**Claimed by:**`) or a status like `in-progress` — the orchestrator must choose and document it.
- Evidence folder `docs/tickets/<spec>/<ticket>-evidence/`: NOT mentioned anywhere on candidate and no such folders exist. It is a convention introduced by the orchestration, not the repo.

## Build / test / lint
- None exist on candidate: nothing to install, build, lint or test. "Pass/fail" is N/A (no test suite).
- Planned (docs/plan.md, spec 01; to be created by ticket 01-01): `Makefile` targets `dev`, `test`, `lint`, `seed`, `gen-client`, `e2e`; `make dev` starts docker compose (Postgres+pgvector, Redis, RustFS, Mailpit, API, worker, Beat, Studio).
  - Backend (`backend/`): uv, Python 3.13, ruff, `mypy --strict`, pytest with 100% line+branch coverage gate (ADR-0008), Alembic up/down round-trip, pip-audit; `@pytest.mark.live` tests outside the gate.
  - Frontend (`frontend/`, pnpm workspace, Node 22): eslint, tsc, Vitest + Testing Library + MSW with 100% coverage, build, API-client drift check, pnpm audit; Playwright + axe e2e against docker compose.
  - Infra: terraform fmt/validate/tflint/checkov/`terraform test`.
  - CI workflows: backend.yml, frontend.yml, infra.yml (+ others in plan.md section on CI).

## Specs
| # | Path | Tickets |
|---|---|---|
| 01 | `docs/specs/01-skeleton-auth-tenancy-spec.md` | 12 |
| 02 | `docs/specs/02-provider-credentials-theme-spec.md` | 6 |
| 03 | `docs/specs/03-projects-knowledge-base-spec.md` | 11 |
| 04 | `docs/specs/04-agents-retrieval-playground-spec.md` | 9 |
| 05 | `docs/specs/05-versioning-project-instructions-spec.md` | 6 |
| 06 | `docs/specs/06-embed-widget-operational-settings-spec.md` | 7 |
| 07 | `docs/specs/07-feedback-logging-comparison-spec.md` | 8 |
| 08 | `docs/specs/08-guardrails-evaluation-spec.md` | 7 |
| 09 | `docs/specs/09-terraform-deploy-spec.md` | 6 |
| 10 | `docs/specs/10-seed-showcase-spec.md` | 6 |

## All tickets (status from ticket file; deps from docs/tickets/README.md index, which matches each ticket's Blocked-by section)
| ID | Title | Path | Status | Blocked by |
|---|---|---|---|---|
| 01-01 | Walking skeleton | `docs/tickets/01-skeleton-auth-tenancy/01-walking-skeleton.md` | ready-for-agent | none |
| 01-02 | Remaining CI gates and Playwright harness | `docs/tickets/01-skeleton-auth-tenancy/02-ci-gates-playwright-harness.md` | ready-for-agent | 01-01 |
| 01-03 | Telemetry with scrubbing | `docs/tickets/01-skeleton-auth-tenancy/03-telemetry-scrubbing.md` | ready-for-agent | 01-01 |
| 01-04 | Sign up, sign in, sign out | `docs/tickets/01-skeleton-auth-tenancy/04-sign-up-sign-in-sign-out.md` | ready-for-agent | 01-01, 01-02 |
| 01-05 | Audit Events and Audit tab | `docs/tickets/01-skeleton-auth-tenancy/05-audit-events.md` | ready-for-agent | 01-04 |
| 01-06 | Sign-in rate limiting and lockout | `docs/tickets/01-skeleton-auth-tenancy/06-sign-in-rate-limiting.md` | ready-for-agent | 01-04 |
| 01-07 | Mailer, password reset and change password | `docs/tickets/01-skeleton-auth-tenancy/07-mailer-password-reset.md` | ready-for-agent | 01-04 |
| 01-08 | Invites and joining an Organisation | `docs/tickets/01-skeleton-auth-tenancy/08-invites-joining.md` | ready-for-agent | 01-05, 01-07 |
| 01-09 | Member management and role enforcement | `docs/tickets/01-skeleton-auth-tenancy/09-member-management-roles.md` | ready-for-agent | 01-08 |
| 01-10 | Organisation switcher | `docs/tickets/01-skeleton-auth-tenancy/10-organisation-switcher.md` | ready-for-agent | 01-08 |
| 01-11 | TOTP MFA | `docs/tickets/01-skeleton-auth-tenancy/11-totp-mfa.md` | ready-for-agent | 01-04 |
| 01-12 | Require MFA policy | `docs/tickets/01-skeleton-auth-tenancy/12-require-mfa-policy.md` | ready-for-agent | 01-09, 01-11 |
| 02-01 | API-key Provider Credentials | `docs/tickets/02-provider-credentials-theme/01-api-key-credentials.md` | ready-for-agent | 01-09, 01-11 |
| 02-02 | Bedrock credentials | `docs/tickets/02-provider-credentials-theme/02-bedrock-credentials.md` | ready-for-agent | 02-01 |
| 02-03 | Model gateway and Default Model | `docs/tickets/02-provider-credentials-theme/03-model-gateway-default-model.md` | ready-for-agent | 02-01 |
| 02-04 | Price table and overrides | `docs/tickets/02-provider-credentials-theme/04-price-table-overrides.md` | ready-for-agent | 02-03 |
| 02-05 | Theme editor | `docs/tickets/02-provider-credentials-theme/05-theme-editor.md` | ready-for-agent | 01-09 |
| 02-06 | Theme logo and avatar | `docs/tickets/02-provider-credentials-theme/06-theme-logo-avatar.md` | ready-for-agent | 02-05, 03-02 |
| 03-01 | Projects and Project page shell | `docs/tickets/03-projects-knowledge-base/01-projects-shell.md` | ready-for-agent | 01-09 |
| 03-02 | Upload a Document to Ready | `docs/tickets/03-projects-knowledge-base/02-upload-document-to-ready.md` | ready-for-agent | 03-01 |
| 03-03 | Document viewer | `docs/tickets/03-projects-knowledge-base/03-document-viewer.md` | ready-for-agent | 03-02 |
| 03-04 | Ingestion failures and limits | `docs/tickets/03-projects-knowledge-base/04-ingestion-failures-limits.md` | ready-for-agent | 03-02 |
| 03-05 | Dedupe, delete and replace edition | `docs/tickets/03-projects-knowledge-base/05-dedupe-delete-replace.md` | ready-for-agent | 03-02 |
| 03-06 | Tags | `docs/tickets/03-projects-knowledge-base/06-tags.md` | ready-for-agent | 03-02 |
| 03-07 | Heuristic ingestion scan | `docs/tickets/03-projects-knowledge-base/07-heuristic-ingestion-scan.md` | ready-for-agent | 03-03 |
| 03-08 | OCR toggle | `docs/tickets/03-projects-knowledge-base/08-ocr-toggle.md` | ready-for-agent | 03-02 |
| 03-09 | Provider Embedding Models | `docs/tickets/03-projects-knowledge-base/09-provider-embedding-models.md` | ready-for-agent | 03-02, 02-03 |
| 03-10 | Re-embed on Embedding Model change | `docs/tickets/03-projects-knowledge-base/10-re-embed-on-model-change.md` | ready-for-agent | 03-09 |
| 03-11 | Permanent Project deletion | `docs/tickets/03-projects-knowledge-base/11-permanent-project-deletion.md` | ready-for-agent | 03-05 |
| 04-01 | Agent and Playground tracer | `docs/tickets/04-agents-retrieval-playground/01-agent-playground-tracer.md` | ready-for-agent | 03-02, 02-03 |
| 04-02 | Markdown editor | `docs/tickets/04-agents-retrieval-playground/02-markdown-editor.md` | ready-for-agent | 04-01 |
| 04-03 | Hybrid retrieval and fallback | `docs/tickets/04-agents-retrieval-playground/03-hybrid-retrieval-fallback.md` | ready-for-agent | 04-01 |
| 04-04 | Tag scoping | `docs/tickets/04-agents-retrieval-playground/04-tag-scoping.md` | ready-for-agent | 04-03, 03-06 |
| 04-05 | Reranker | `docs/tickets/04-agents-retrieval-playground/05-reranker.md` | ready-for-agent | 04-03 |
| 04-06 | Citations and Trace drawer | `docs/tickets/04-agents-retrieval-playground/06-citations-trace.md` | ready-for-agent | 04-03, 02-04 |
| 04-07 | Full AgentConfig editor | `docs/tickets/04-agents-retrieval-playground/07-full-agentconfig-editor.md` | ready-for-agent | 04-01 |
| 04-08 | Playground errors and reset | `docs/tickets/04-agents-retrieval-playground/08-playground-errors-reset.md` | ready-for-agent | 04-01 |
| 04-09 | Agent Archive and delete | `docs/tickets/04-agents-retrieval-playground/09-agent-archive-delete.md` | ready-for-agent | 04-01 |
| 05-01 | Project Instructions Versions | `docs/tickets/05-versioning-project-instructions/01-project-instructions-versions.md` | ready-for-agent | 04-02 |
| 05-02 | Publish Agent to Live Version | `docs/tickets/05-versioning-project-instructions/02-publish-agent-live-version.md` | ready-for-agent | 05-01, 04-07 |
| 05-03 | Revert via Live History | `docs/tickets/05-versioning-project-instructions/03-revert-live-history.md` | ready-for-agent | 05-02 |
| 05-04 | Diffs and Draft management | `docs/tickets/05-versioning-project-instructions/04-diffs-draft-management.md` | ready-for-agent | 05-02 |
| 05-05 | Bulk publish, bulk revert and Instructions rollout | `docs/tickets/05-versioning-project-instructions/05-bulk-publish-revert.md` | ready-for-agent | 05-03 |
| 05-06 | Playground Instructions picker | `docs/tickets/05-versioning-project-instructions/06-playground-instructions-picker.md` | ready-for-agent | 05-01 |
| 06-01 | Embed tracer | `docs/tickets/06-embed-widget-operational-settings/01-embed-tracer.md` | ready-for-agent | 05-02 |
| 06-02 | Operational Settings and origin enforcement | `docs/tickets/06-embed-widget-operational-settings/02-operational-settings-origins.md` | ready-for-agent | 06-01 |
| 06-03 | Branded widget | `docs/tickets/06-embed-widget-operational-settings/03-branded-widget.md` | ready-for-agent | 06-01, 02-05 |
| 06-04 | Resume and Conversation lifecycle | `docs/tickets/06-embed-widget-operational-settings/04-resume-lifecycle.md` | ready-for-agent | 06-01 |
| 06-05 | Rate limits | `docs/tickets/06-embed-widget-operational-settings/05-rate-limits.md` | ready-for-agent | 06-02 |
| 06-06 | Token Budget | `docs/tickets/06-embed-widget-operational-settings/06-token-budget.md` | ready-for-agent | 06-05 |
| 06-07 | WCAG 2.2 AA widget | `docs/tickets/06-embed-widget-operational-settings/07-wcag-aa.md` | ready-for-agent | 06-03 |
| 07-01 | Conversations viewer | `docs/tickets/07-feedback-logging-comparison/01-conversations-viewer.md` | ready-for-agent | 06-01, 04-06 |
| 07-02 | Message Feedback | `docs/tickets/07-feedback-logging-comparison/02-message-feedback.md` | ready-for-agent | 07-01 |
| 07-03 | Conversation Rating | `docs/tickets/07-feedback-logging-comparison/03-conversation-rating.md` | ready-for-agent | 07-02 |
| 07-04 | Rollups and Version KPIs | `docs/tickets/07-feedback-logging-comparison/04-rollups-version-kpis.md` | ready-for-agent | 07-03 |
| 07-05 | Version comparison | `docs/tickets/07-feedback-logging-comparison/05-version-comparison.md` | ready-for-agent | 07-04, 05-04 |
| 07-06 | Time series | `docs/tickets/07-feedback-logging-comparison/06-time-series.md` | ready-for-agent | 07-04 |
| 07-07 | Retention and tombstones | `docs/tickets/07-feedback-logging-comparison/07-retention-tombstones.md` | ready-for-agent | 07-04, 03-05 |
| 07-08 | Organisation cost page | `docs/tickets/07-feedback-logging-comparison/08-organisation-cost.md` | ready-for-agent | 07-04 |
| 08-01 | Input Guardrail: local classifier, block mode | `docs/tickets/08-guardrails-evaluation/01-input-guardrail-block.md` | ready-for-agent | 04-06, 06-01 |
| 08-02 | Warn and log modes | `docs/tickets/08-guardrails-evaluation/02-warn-log-modes.md` | ready-for-agent | 08-01 |
| 08-03 | LLM classifier | `docs/tickets/08-guardrails-evaluation/03-llm-classifier.md` | ready-for-agent | 08-01 |
| 08-04 | Canary token | `docs/tickets/08-guardrails-evaluation/04-canary-token.md` | ready-for-agent | 04-06 |
| 08-05 | Classifier-based ingestion scan | `docs/tickets/08-guardrails-evaluation/05-classifier-ingestion-scan.md` | ready-for-agent | 08-01, 03-07, 04-03 |
| 08-06 | Guardrail analytics and alerts | `docs/tickets/08-guardrails-evaluation/06-guardrail-analytics-alerts.md` | ready-for-agent | 08-01, 07-04, 06-06 |
| 08-07 | Attack evaluation suite | `docs/tickets/08-guardrails-evaluation/07-attack-eval-suite.md` | ready-for-agent | 08-02, 08-04, 08-05 |
| 09-01 | State bootstrap and CI OIDC | `docs/tickets/09-terraform-deploy/01-state-bootstrap-oidc.md` | ready-for-agent | 01-02 |
| 09-02 | Network module | `docs/tickets/09-terraform-deploy/02-network-module.md` | ready-for-agent | 01-02 |
| 09-03 | Data modules | `docs/tickets/09-terraform-deploy/03-data-modules.md` | ready-for-agent | 09-02 |
| 09-04 | Compute module | `docs/tickets/09-terraform-deploy/04-compute-module.md` | ready-for-agent | 09-03 |
| 09-05 | CDN module | `docs/tickets/09-terraform-deploy/05-cdn-module.md` | ready-for-agent | 09-04 |
| 09-06 | Demo environment and deploy workflow | `docs/tickets/09-terraform-deploy/06-demo-env-deploy.md` | ready-for-agent | 09-01, 09-05, 06-01 |
| 10-01 | Seed foundation | `docs/tickets/10-seed-showcase/01-seed-foundation.md` | ready-for-agent | 03-06, 02-05, 04-07 |
| 10-02 | Seeded history | `docs/tickets/10-seed-showcase/02-seeded-history.md` | ready-for-agent | 10-01, 05-05, 07-04 |
| 10-03 | Demo host pages | `docs/tickets/10-seed-showcase/03-demo-host-pages.md` | ready-for-agent | 10-01, 06-06 |
| 10-04 | Attack panel | `docs/tickets/10-seed-showcase/04-attack-panel.md` | ready-for-agent | 10-02, 08-01, 08-04 |
| 10-05 | Seed in AWS | `docs/tickets/10-seed-showcase/05-seed-in-aws.md` | ready-for-agent | 10-02, 09-06 |
| 10-06 | README and automated demo | `docs/tickets/10-seed-showcase/06-readme-demo.md` | ready-for-agent | 10-03, 10-04 |

## Unblocked frontier
Done tickets: none. Claimed tickets: none. Frontier = tickets with no blockers:
- `01-skeleton-auth-tenancy/01-01` Walking skeleton (deps: none)

Next frontier once 01-01 is done: 01-02 (CI gates + Playwright), 01-03 (telemetry scrubbing). After 01-02: 01-04, 09-01, 09-02.
