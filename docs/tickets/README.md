# Tickets

Tracer-bullet tickets split from the [slice specs](../specs/README.md). Ticket IDs are `<spec>-<NN>`, and blockers can point into other specs.
Work the **frontier**: any ticket whose blockers are all done. `01-01` and `11-01` are the only tickets with no blockers.

New tickets start from [TEMPLATE.md](./TEMPLATE.md). Its standing criteria apply to every ticket: new Studio UI uses the [design system](../design/README.md) (the palette ratchet enforces it), tests sit at the highest seam with 100% coverage, and the glossary and ADRs stay current.

## 01: Skeleton, CI, auth and tenancy

| Ticket | Title | Blocked by |
|---|---|---|
| `01-01` | [Walking skeleton](./01-skeleton-auth-tenancy/01-walking-skeleton.md) | none |
| `01-02` | [Remaining CI gates and Playwright harness](./01-skeleton-auth-tenancy/02-ci-gates-playwright-harness.md) | 01-01 |
| `01-03` | [Telemetry with scrubbing](./01-skeleton-auth-tenancy/03-telemetry-scrubbing.md) | 01-01 |
| `01-04` | [Sign up, sign in, sign out](./01-skeleton-auth-tenancy/04-sign-up-sign-in-sign-out.md) | 01-01, 01-02 |
| `01-05` | [Audit Events and Audit tab](./01-skeleton-auth-tenancy/05-audit-events.md) | 01-04 |
| `01-06` | [Sign-in rate limiting and lockout](./01-skeleton-auth-tenancy/06-sign-in-rate-limiting.md) | 01-04 |
| `01-07` | [Mailer, password reset and change password](./01-skeleton-auth-tenancy/07-mailer-password-reset.md) | 01-04 |
| `01-08` | [Invites and joining an Organisation](./01-skeleton-auth-tenancy/08-invites-joining.md) | 01-05, 01-07 |
| `01-09` | [Member management and role enforcement](./01-skeleton-auth-tenancy/09-member-management-roles.md) | 01-08 |
| `01-10` | [Organisation switcher](./01-skeleton-auth-tenancy/10-organisation-switcher.md) | 01-08 |
| `01-11` | [TOTP MFA](./01-skeleton-auth-tenancy/11-totp-mfa.md) | 01-04 |
| `01-12` | [Require MFA policy](./01-skeleton-auth-tenancy/12-require-mfa-policy.md) | 01-09, 01-11 |

## 02: Provider Credentials and Theme

| Ticket | Title | Blocked by |
|---|---|---|
| `02-01` | [API-key Provider Credentials](./02-provider-credentials-theme/01-api-key-credentials.md) | 01-09, 01-11 |
| `02-02` | [Bedrock credentials](./02-provider-credentials-theme/02-bedrock-credentials.md) | 02-01 |
| `02-03` | [Model gateway and Default Model](./02-provider-credentials-theme/03-model-gateway-default-model.md) | 02-01 |
| `02-04` | [Price table and overrides](./02-provider-credentials-theme/04-price-table-overrides.md) | 02-03 |
| `02-05` | [Theme editor](./02-provider-credentials-theme/05-theme-editor.md) | 01-09 |
| `02-06` | [Theme logo and avatar](./02-provider-credentials-theme/06-theme-logo-avatar.md) | 02-05, 03-02 |

## 03: Projects and Knowledge Base

| Ticket | Title | Blocked by |
|---|---|---|
| `03-01` | [Projects and Project page shell](./03-projects-knowledge-base/01-projects-shell.md) | 01-09 |
| `03-02` | [Upload a Document to Ready](./03-projects-knowledge-base/02-upload-document-to-ready.md) | 03-01 |
| `03-03` | [Document viewer](./03-projects-knowledge-base/03-document-viewer.md) | 03-02 |
| `03-04` | [Ingestion failures and limits](./03-projects-knowledge-base/04-ingestion-failures-limits.md) | 03-02 |
| `03-05` | [Dedupe, delete and replace edition](./03-projects-knowledge-base/05-dedupe-delete-replace.md) | 03-02 |
| `03-06` | [Tags](./03-projects-knowledge-base/06-tags.md) | 03-02 |
| `03-07` | [Heuristic ingestion scan](./03-projects-knowledge-base/07-heuristic-ingestion-scan.md) | 03-03 |
| `03-08` | [OCR toggle](./03-projects-knowledge-base/08-ocr-toggle.md) | 03-02 |
| `03-09` | [Provider Embedding Models](./03-projects-knowledge-base/09-provider-embedding-models.md) | 03-02, 02-03 |
| `03-10` | [Re-embed on Embedding Model change](./03-projects-knowledge-base/10-re-embed-on-model-change.md) | 03-09 |
| `03-11` | [Permanent Project deletion](./03-projects-knowledge-base/11-permanent-project-deletion.md) | 03-05 |

## 04: Agents, retrieval and Playground

| Ticket | Title | Blocked by |
|---|---|---|
| `04-01` | [Agent and Playground tracer](./04-agents-retrieval-playground/01-agent-playground-tracer.md) | 03-02, 02-03 |
| `04-02` | [Markdown editor](./04-agents-retrieval-playground/02-markdown-editor.md) | 04-01 |
| `04-03` | [Hybrid retrieval and fallback](./04-agents-retrieval-playground/03-hybrid-retrieval-fallback.md) | 04-01 |
| `04-04` | [Tag scoping](./04-agents-retrieval-playground/04-tag-scoping.md) | 04-03, 03-06 |
| `04-05` | [Reranker](./04-agents-retrieval-playground/05-reranker.md) | 04-03 |
| `04-06` | [Citations and Trace drawer](./04-agents-retrieval-playground/06-citations-trace.md) | 04-03, 02-04 |
| `04-07` | [Full AgentConfig editor](./04-agents-retrieval-playground/07-full-agentconfig-editor.md) | 04-01 |
| `04-08` | [Playground errors and reset](./04-agents-retrieval-playground/08-playground-errors-reset.md) | 04-01 |
| `04-09` | [Agent Archive and delete](./04-agents-retrieval-playground/09-agent-archive-delete.md) | 04-01 |

## 05: Versioning and Project Instructions

| Ticket | Title | Blocked by |
|---|---|---|
| `05-01` | [Project Instructions Versions](./05-versioning-project-instructions/01-project-instructions-versions.md) | 04-02 |
| `05-02` | [Publish Agent to Live Version](./05-versioning-project-instructions/02-publish-agent-live-version.md) | 05-01, 04-07 |
| `05-03` | [Revert via Live History](./05-versioning-project-instructions/03-revert-live-history.md) | 05-02 |
| `05-04` | [Diffs and Draft management](./05-versioning-project-instructions/04-diffs-draft-management.md) | 05-02 |
| `05-05` | [Bulk publish, bulk revert and Instructions rollout](./05-versioning-project-instructions/05-bulk-publish-revert.md) | 05-03 |
| `05-06` | [Playground Instructions picker](./05-versioning-project-instructions/06-playground-instructions-picker.md) | 05-01 |

## 06: Embed, widget and Operational Settings

| Ticket | Title | Blocked by |
|---|---|---|
| `06-01` | [Embed tracer](./06-embed-widget-operational-settings/01-embed-tracer.md) | 05-02 |
| `06-02` | [Operational Settings and origin enforcement](./06-embed-widget-operational-settings/02-operational-settings-origins.md) | 06-01 |
| `06-03` | [Branded widget](./06-embed-widget-operational-settings/03-branded-widget.md) | 06-01, 02-05 |
| `06-04` | [Resume and Conversation lifecycle](./06-embed-widget-operational-settings/04-resume-lifecycle.md) | 06-01 |
| `06-05` | [Rate limits](./06-embed-widget-operational-settings/05-rate-limits.md) | 06-02 |
| `06-06` | [Token Budget](./06-embed-widget-operational-settings/06-token-budget.md) | 06-05 |
| `06-07` | [WCAG 2.2 AA widget](./06-embed-widget-operational-settings/07-wcag-aa.md) | 06-03 |

## 07: Feedback, logging and comparison

| Ticket | Title | Blocked by |
|---|---|---|
| `07-01` | [Conversations viewer](./07-feedback-logging-comparison/01-conversations-viewer.md) | 06-01, 04-06 |
| `07-02` | [Message Feedback](./07-feedback-logging-comparison/02-message-feedback.md) | 07-01 |
| `07-03` | [Conversation Rating](./07-feedback-logging-comparison/03-conversation-rating.md) | 07-02 |
| `07-04` | [Rollups and Version KPIs](./07-feedback-logging-comparison/04-rollups-version-kpis.md) | 07-03 |
| `07-05` | [Version comparison](./07-feedback-logging-comparison/05-version-comparison.md) | 07-04, 05-04 |
| `07-06` | [Time series](./07-feedback-logging-comparison/06-time-series.md) | 07-04 |
| `07-07` | [Retention and tombstones](./07-feedback-logging-comparison/07-retention-tombstones.md) | 07-04, 03-05 |
| `07-08` | [Organisation cost page](./07-feedback-logging-comparison/08-organisation-cost.md) | 07-04 |

## 08: Guardrails and evaluation

| Ticket | Title | Blocked by |
|---|---|---|
| `08-01` | [Input Guardrail: local classifier, block mode](./08-guardrails-evaluation/01-input-guardrail-block.md) | 04-06, 06-01 |
| `08-02` | [Warn and log modes](./08-guardrails-evaluation/02-warn-log-modes.md) | 08-01 |
| `08-03` | [LLM classifier](./08-guardrails-evaluation/03-llm-classifier.md) | 08-01 |
| `08-04` | [Canary token](./08-guardrails-evaluation/04-canary-token.md) | 04-06 |
| `08-05` | [Classifier-based ingestion scan](./08-guardrails-evaluation/05-classifier-ingestion-scan.md) | 08-01, 03-07, 04-03 |
| `08-06` | [Guardrail analytics and alerts](./08-guardrails-evaluation/06-guardrail-analytics-alerts.md) | 08-01, 07-04, 06-06 |
| `08-07` | [Attack evaluation suite](./08-guardrails-evaluation/07-attack-eval-suite.md) | 08-02, 08-04, 08-05 |

## 09: Terraform and deploy

| Ticket | Title | Blocked by |
|---|---|---|
| `09-01` | [State bootstrap and CI OIDC](./09-terraform-deploy/01-state-bootstrap-oidc.md) | 01-02 |
| `09-02` | [Network module](./09-terraform-deploy/02-network-module.md) | 01-02 |
| `09-03` | [Data modules](./09-terraform-deploy/03-data-modules.md) | 09-02 |
| `09-04` | [Compute module](./09-terraform-deploy/04-compute-module.md) | 09-03 |
| `09-05` | [CDN module](./09-terraform-deploy/05-cdn-module.md) | 09-04 |
| `09-06` | [Demo environment and deploy workflow](./09-terraform-deploy/06-demo-env-deploy.md) | 09-01, 09-05, 06-01 |

## 10: Seed data and showcase

| Ticket | Title | Blocked by |
|---|---|---|
| `10-01` | [Seed foundation](./10-seed-showcase/01-seed-foundation.md) | 03-06, 02-05, 04-07 |
| `10-02` | [Seeded history](./10-seed-showcase/02-seeded-history.md) | 10-01, 05-05, 07-04 |
| `10-03` | [Demo host pages](./10-seed-showcase/03-demo-host-pages.md) | 10-01, 06-06 |
| `10-04` | [Attack panel](./10-seed-showcase/04-attack-panel.md) | 10-02, 08-01, 08-04 |
| `10-05` | [Seed in AWS](./10-seed-showcase/05-seed-in-aws.md) | 10-02, 09-06 |
| `10-06` | [README and automated demo](./10-seed-showcase/06-readme-demo.md) | 10-03, 10-04 |

## 11: Studio design system and reskin

These tickets are worked on the `candidate-reskin` branch: each ticket branches from it and merges back into it, not into `candidate`. `11-01` begins by merging `candidate` in. When `11-13` is done, `candidate-reskin` merges into `candidate`.

| Ticket | Title | Blocked by |
|---|---|---|
| `11-01` | [Palette ratchet and design system round 2](./11-studio-design/01-ratchet-design-system-round-2.md) | none |
| `11-02` | [Foundation: tokens, fonts and Appearance](./11-studio-design/02-foundation.md) | 11-01 |
| `11-03` | [Colour codemod](./11-studio-design/03-colour-codemod.md) | 11-02 |
| `11-04` | [Shell, breadcrumb and navigation test helpers](./11-studio-design/04-shell-navigation.md) | 11-03 |
| `11-05` | [Project frame](./11-studio-design/05-project-frame.md) | 11-04 |
| `11-06` | [Documents and Document viewer](./11-studio-design/06-documents.md) | 11-05 |
| `11-07` | [Instructions, Versions and rollout dialog](./11-studio-design/07-instructions-versions-rollout.md) | 11-05 |
| `11-08` | [Agent page and its four views](./11-studio-design/08-agent-views.md) | 11-05 |
| `11-09` | [Agents list and bulk actions](./11-studio-design/09-agents-list-bulk.md) | 11-05 |
| `11-10` | [Conversations and Analytics](./11-studio-design/10-conversations-analytics.md) | 11-05, 11-08 |
| `11-11` | [Organisation settings](./11-studio-design/11-organisation-settings.md) | 11-04 |
| `11-12` | [Signed-out pages, profile, security and status](./11-studio-design/12-signed-out-account-pages.md) | 11-04 |
| `11-13` | [Polish: narrow screens, accessibility and screenshots](./11-studio-design/13-polish.md) | 11-06, 11-07, 11-08, 11-09, 11-10, 11-11, 11-12 |
