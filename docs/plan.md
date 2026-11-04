# RAG Agent Studio — Build Plan

Organisations use RAG Agent Studio to build Agents grounded in a Knowledge Base, inside isolated Projects, then publish and embed them on their own sites. Agents are versioned, can be reverted, resist abuse, and are measured by Version.

This is an interview capstone. It must run end-to-end locally with `docker compose`, be deployable to a short-lived AWS environment with Terraform, and keep 100% line and branch test coverage from the first commit.

**Read first**
- [`GLOSSARY.md`](../GLOSSARY.md): the domain language. Code, UI copy and docs use these terms and avoid the listed alternatives.
- [`docs/adr/`](./adr): the decisions behind the less obvious choices. Don't reverse one without writing a superseding ADR.

---

## 1. Scope

### In scope
- **Accounts:** Organisations and Members with Owner and Editor roles. Email and password sign-in, invites, password reset, TOTP MFA that Owners can make mandatory, and login rate limiting.
- **Provider Credentials:** Anthropic, OpenAI, Bedrock (role or access keys) and Voyage, with envelope encryption and a live check when saved. The Organisation sets a Default Model.
- **Projects:**
  - Knowledge Base: upload Documents, process them with Docling and Celery, use Tags, and view and manage them.
  - Embedding Model: chosen per Project. Switching it re-embeds in the background.
  - Project Instructions: Draft, Versions and a Current Version.
- **Agents:** highly configurable, with Draft, immutable Versions, a Live Version, Live History, bulk publish and bulk revert, the Playground, Archive, and Operational Settings.
- **Embed:** an Embed Snippet backed by an iframe widget. Allowed Origins are enforced, the Theme applies with per-Agent overrides, the widget targets WCAG 2.2 AA, and Conversations resume.
- **Guardrails:** spotlighting, an input classifier (local by default, LLM optional), a canary token, ingestion scanning, and an attack evaluation suite.
- **Feedback and analytics:**
  - Visitor feedback: Message Feedback and Conversation Ratings.
  - Logging: every Agent Message gets a full Trace, a Conversation viewer, and cost frozen when the Message is written.
  - Comparison by Version.
- **Operations:** a Retention Window, Audit Events, and a pluggable mailer.
- **Platform:**
  - Terraform for AWS and GitHub Actions CI/CD.
  - Observability with Logfire and OpenTelemetry.
  - Seed data, including an attack panel.

### Out of scope (for now)
SSO, identified Visitors, tools that act outside the conversation, versioned Documents, inferred sentiment analysis, XLSX and image ingestion, full i18n bundles, a session-list UI, multiple regions, and a custom domain (supported later through a variable).

---

## 2. Architecture

```
                         ┌──────────────── CloudFront (*.cloudfront.net) ────────────────┐
 Member browser ───────▶ │ /                → S3: Studio SPA                             │
 Host site + embed.js ─▶ │ /embed.js, /widget/assets/* → S3: widget bundle               │
   └─ iframe ──────────▶ │ /widget/a/{publicId} → ALB → api (HTML shell + CSP header)    │
                         │ /api/*           → ALB → api                                   │
                         └───────────────────────────────────────────────────────────────┘
                                              │
         ┌────────────────────────────────────┼─────────────────────────────────┐
         ▼                                    ▼                                 ▼
   api (FastAPI, Fargate)            worker (Celery, Fargate)          beat (Celery Beat)
   - Studio REST API                 - Docling convert + chunk          - retention purge
   - Widget API + SSE chat           - embed (local / provider)         - daily usage rollups
   - Pydantic AI agent runtime       - ingestion guardrail scan         - budget reset
   - local embed + classifier        - re-embed jobs, email send
         │                                    │
         └──────────────┬─────────────────────┘
                        ▼
      RDS Postgres 16 + pgvector     ElastiCache Redis           S3 (RustFS locally)
      (all relational + vectors)     (broker, rate limits,       (Documents, Docling output)
                                      budgets, SSE fan-out)
      KMS (wraps credential data keys)   Secrets Manager (platform secrets)
```

**Why it looks like this:** ADR-0001 (pgvector), ADR-0004 (iframe embed), ADR-0010 (AWS runtime) and ADR-0011 (one CloudFront distribution).

### Chat request pipeline
1. **Widget boot.** `embed.js` reads `data-agent="pub_…"` and injects an iframe pointing at `/widget/a/{publicId}`. The API answers with the HTML shell, a `Content-Security-Policy: frame-ancestors <Allowed Origins>` header, the resolved Theme as CSS variables, and a bootstrap token. A Conversation token stored in the iframe's (partitioned) storage resumes the Conversation if there was activity in the last 24 hours.
2. **Admission.** The API validates the Conversation token, then checks the per-token and per-IP rate limits and the Agent's daily Token Budget in Redis. If any fails, the widget shows the Agent's configured "temporarily unavailable" text.
3. **Input Guardrail.** The local classifier runs, plus the LLM classifier if enabled. The outcome is block, warn or log, depending on the Agent Version's setting.
4. **Retrieval.** The query is embedded with the Project's active Embedding Model. Hybrid search (pgvector plus `tsvector`, fused with RRF) runs, filtered by `project_id` and the Agent's Tags, followed by the optional reranker and a minimum-relevance threshold.
5. **Prompt assembly.** In order:
   - the platform preamble, including the canary token and the rules for treating input as untrusted;
   - the **pinned** Project Instructions Version;
   - the Agent system prompt;
   - the remembered turns;
   - retrieved Chunks and the Visitor input, each wrapped in labelled, delimited data blocks (spotlighting).
6. **Generation.** A Pydantic AI agent streams the reply over SSE. The output filter holds back a trailing window the length of the canary token so a leak spread across stream chunks is still caught. If the canary appears, the stream is cut and replaced with the fallback text, and the event is logged.
7. **Persist.** The Message is saved with its Trace: provider, model, Agent Version, tokens (input, output, cached), cost frozen from the price table, time to first token and total latency, retrieved Chunks with scores and whether each was cited, and Guardrail outcomes. Usage counters are then incremented.

### Ingestion pipeline (Celery)
1. **Upload.** The Studio gets a presigned PUT URL and uploads straight to S3. The API then creates the Document with status `Queued`, deduplicating by content hash within the Project.
2. **Convert.** Status becomes `Processing`. Docling converts the file (OCR only if the Project's OCR toggle is on), and the markdown output is stored in S3.
3. **Chunk.** `HybridChunker` splits the output, using the tokenizer that matches the Project's Embedding Model.
4. **Embed and scan.** Chunks are embedded, and the ingestion Guardrail scan flags Chunks that look like instructions.
5. **Store.** Chunks are written in one transaction, then the status becomes `Ready`.
6. **Failures.** Any failure sets `Failed` with an error message, and the Document can be retried. Uploading a newer edition of a Document replaces its Chunks atomically under the same Document identity.
7. **Changing the Embedding Model.** A re-embed job writes new vectors alongside the old ones, then switches the Project's active model in one step and deletes the old vectors (ADR-0002).

---

## 3. Domain data model (initial sketch)

| Area | Tables |
|---|---|
| Tenancy | `organisations` (default credential + model, retention days, require_mfa), `members`, `memberships` (role), `invites`, `password_reset_tokens`, `member_mfa`, `audit_events` |
| Models | `provider_credentials` (provider, auth kind, ciphertext, wrapped data key, masked suffix, capabilities, last_verified_at, price overrides) |
| Theme | `themes` (Organisation-level tokens, launcher, mode), `agent_theme_overrides` (colours, avatar) |
| Knowledge | `projects` (active + pending Embedding Model, OCR flag, current Project Instructions Version, archived_at), `tags`, `documents`, `document_tags`, `chunks` (project_id, document_id, text, `vector`, embedding model, `tsvector`, headings/page metadata, guardrail flags), `embedding_jobs` |
| Instructions | `project_instruction_drafts`, `project_instruction_versions` (number, markdown, author) |
| Agents | `agents` (public_id, live_version_id, archived_at), `agent_drafts` (config), `agent_versions` (number, config, pinned Project Instructions Version, author), `live_history`, `agent_operational_settings` (Allowed Origins, rate limits, Token Budget, unavailable text) |
| Conversations | `conversations` (agent, is_playground, visitor token hash, last_activity), `messages` (role, content, purged_at, agent_version_id, provider, model, tokens, cost, latencies, guardrail outcomes), `message_retrievals` (chunk_id nullable, document-name tombstone, score, cited), `message_feedback`, `conversation_ratings` (+ change log) |
| Analytics | `usage_daily` (rollups per Agent Version per day), `model_prices` (seeded from the repo price table, with dates prices took effect) |

**Typing.** Agent config is a single Pydantic model, `AgentConfig`, stored as `jsonb` and validated both ways. It contains:
- **Behaviour:** system prompt, model override, temperature, max tokens, remembered turns, fallback text.
- **Retrieval:** top-k, hybrid weighting, minimum score, Tags, reranker, citations.
- **Experience:** display name, avatar, greeting, starter questions, UI string overrides, when to ask for a Conversation Rating.
- **Guardrails:** input mode and the LLM classifier.

Operational Settings and Theme overrides live **outside** `AgentConfig` (ADR-0009).

**Isolation.** Every query below the Organisation level is scoped through repository functions that require an `organisation_id` and/or `project_id`. Tests assert that data from one tenant never crosses into another.

### Assumptions to confirm
These were not explicitly settled during the design interview. They are the defaults unless changed:
- **A reply uses whatever Agent Version is Live when it is generated**, not the Version Live when the Conversation started. That way a revert takes effect immediately during an incident. Message Feedback is attributed to the Message's Version. A Conversation Rating is attributed to the Version of the last Agent Message before the rating.
- **Archived Agents** return a friendly "no longer available" shell instead of a broken iframe.

---

## 4. Repository layout

```
/
├── GLOSSARY.md
├── docs/{plan.md, adr/}
├── docker-compose.yml          # postgres+pgvector, redis, rustfs, mailpit, api, worker, beat, studio, widget
├── Makefile                    # dev, test, lint, seed, gen-client, e2e
├── backend/                    # uv, Python 3.13, ruff, mypy --strict
│   ├── app/
│   │   ├── core/               # settings (pydantic-settings), db, security, crypto, telemetry
│   │   ├── tenancy/ models/ knowledge/ agents/ conversations/ analytics/ guardrails/ embed/ audit/
│   │   ├── runtime/            # Pydantic AI agent assembly, retrieval, streaming, canary filter
│   │   └── worker/             # Celery app + tasks
│   ├── migrations/             # Alembic
│   └── tests/{unit,integration,eval}/
├── frontend/                   # pnpm workspace, Node 22 LTS
│   ├── apps/studio/            # Vite, React 19, TanStack Router + Query, Tailwind, shadcn/ui, Recharts
│   ├── apps/widget/            # iframe app + embed.js loader
│   ├── packages/ui/            # Theme-token-driven primitives; TipTap markdown editor
│   └── packages/api-client/    # generated from FastAPI OpenAPI; drift-checked in CI
├── infra/
│   ├── modules/{network,database,cache,storage,ecs,cdn,kms,ci-oidc}/
│   └── envs/demo/
└── .github/workflows/
```

---

## 5. Engineering conventions

- **Coverage (ADR-0008):** 100% lines and branches in both `backend/` and `frontend/`, enforced in CI. The only exclusions are `__main__` blocks, the generated client and migrations. Migrations get their own upgrade/downgrade round-trip test.
- **Test seams:**
  - Model calls go through Pydantic AI `TestModel`/`FunctionModel`. Docling is replaced by a fake converter.
  - Embeddings and the classifier sit behind interfaces with deterministic fakes.
  - S3 is tested against RustFS in integration tests. Postgres and Redis are real service containers.
  - Tests against real providers are marked `@pytest.mark.live`, run nightly, and are outside the coverage gate.
- **Frontend testing:** Vitest and Testing Library for units, with MSW for API mocks. Playwright runs end-to-end against `docker compose`, including `axe` accessibility checks on the widget.
- **Markdown everywhere:** every prompt or context field uses the TipTap markdown editor and is stored as markdown.
- **Telemetry hygiene:** OpenTelemetry via Logfire, exported to Logfire when a token is set and to the console otherwise. A scrubbing processor removes Message text and secrets, and a test asserts that it does.
- **Audit:** every write in the Audit Event list goes through one `audit.record()` call, which stores who, what, when and before/after values, with secrets redacted.
- **Glossary discipline:** UI copy, API resource names and module names use `GLOSSARY.md` terms. New domain terms are added to the glossary in the same PR that introduces them.

---

## 6. CI/CD (GitHub Actions)

| Workflow | Runs |
|---|---|
| `backend.yml` | ruff, mypy, pytest + coverage gate (Postgres/Redis services), Alembic round-trip, pip-audit |
| `frontend.yml` | eslint, tsc, Vitest + coverage gate, build, api-client drift check, pnpm audit |
| `e2e.yml` | `docker compose up`, seed, Playwright (upload → Ready → publish → embed → chat → feedback), axe |
| `guardrails-eval.yml` | attack-prompt suite against mocked model (PR); against real model nightly if secrets exist |
| `infra.yml` | terraform fmt / validate / tflint / checkov / `terraform test`; `plan` on PR **only if** the OIDC role secret is configured |
| `security.yml` | gitleaks, Trivy image scan |
| `deploy.yml` | on `main`: build + push images to ECR (when AWS configured); manual `workflow_dispatch` to `apply` / `destroy` `envs/demo` |

---

## 7. Delivery slices

Each slice is a vertical increment. It merges only with green CI, 100% coverage, glossary and ADRs updated, and a short demo note in the PR.

### Slice 1: Skeleton, CI, auth and tenancy
- Monorepo scaffolding, `docker compose`, Makefile, and settings via `pydantic-settings`.
- FastAPI app, SQLAlchemy 2 and Alembic, Celery app wiring, OpenTelemetry/Logfire.
- Pluggable mailer: Mailpit locally, console in tests, SES when configured.
- Member sign-up, which creates an Organisation with the new Member as Owner.
- Sign-in and sign-out with httpOnly cookie sessions, argon2, login rate limiting, and password reset.
- Invites by email and copyable link. Owner and Editor roles. Organisation switcher. TOTP MFA, plus "require MFA" for the Organisation.
- Audit Event table and Audit tab (initially recording member events).
- Studio shell: layout, navigation, auth screens, members page. Generated API client.
- All CI workflows present. Terraform modules stubbed so `fmt/validate/tflint/checkov` pass.
- **Done when:** a new Member signs up, invites an Editor via Mailpit, enables MFA, and every gate in CI is green.

### Slice 2: Provider Credentials and Theme
- Envelope encryption service: a KMS adapter in AWS, a local key-file adapter otherwise (ADR-0006).
- Credentials for Anthropic, OpenAI and Voyage (API key) and Bedrock (role ARN plus external ID, or access keys plus region).
- A capability matrix, a live check on save with `last_verified_at`, masked display, rotation and deletion. All of it audited.
- Default Model for the Organisation. Price table seeded from the repo, with per-credential overrides.
- Theme editor: colour tokens, radius, curated fonts, logo, light/dark/auto, launcher type and position. Live preview and a contrast warning.
- **Done when:** an Owner adds each credential type (exercised against fakes), picks a Default Model, styles a Theme and sees the preview, with no secret ever returned by the API.

### Slice 3: Projects and Knowledge Base
- Project CRUD and Archive. Tags. OCR toggle. Embedding Model choice: local `multilingual-e5-small` or a provider.
- Presigned uploads to RustFS/S3. Document statuses, retry, delete, dedupe by content hash, and replacing an edition.
- Celery ingestion: Docling conversion, `HybridChunker`, embedding, ingestion Guardrail scan, transactional Chunk write.
- Document viewer: rendered markdown next to its Chunks, with Guardrail flags and Tags.
- Re-embed job when the Embedding Model changes, with progress UI.
- **Done when:** uploading the seed handbook reaches `Ready`, its Chunks are viewable, a planted "ignore previous instructions" Chunk is flagged, and switching the Embedding Model re-embeds without any downtime.

### Slice 4: Agents, retrieval and Playground
- `AgentConfig` model, Agent CRUD, and a Draft editor (TipTap) covering every config group.
- Retrieval service: hybrid search with RRF, Tag scoping, threshold, optional reranker, citations.
- Pydantic AI runtime: prompt assembly with spotlighting, SSE streaming, remembered turns.
- Playground: chat with the Draft against a chosen Project Instructions Version (Instructions are still a plain field in this slice), with an inline Trace panel.
- Message and Trace persistence. Playground Conversations are flagged.
- **Done when:** an Editor configures an Agent, asks a question in the Playground, sees a streamed answer with citations, and inspects its Trace.

### Slice 5: Versioning and Project Instructions
- Project Instructions: Draft, Versions, Current Version, publish and revert.
- Agent publish creates an immutable Version pinned to the chosen Instructions Version (Current by default). Live pointer, Live History, revert by walking the Live History.
- Bulk dialog: multi-select a Project's Agents to publish (from **Live** config plus the chosen Instructions Version) or revert. Badges show Agents with unpublished Draft changes and "N Agents behind" the Current Instructions Version.
- Version history view with diffs between Versions. Publish and revert are audited.
- **Done when:** publishing Instructions v2, bulk-adopting it on some Agents, then reverting one Agent restores both its config and its pinned Instructions.

### Slice 6: Embed, widget and Operational Settings
- `embed.js` loader, the widget app, and the HTML shell served by the API with `frame-ancestors` from Allowed Origins.
- Bootstrap and Conversation tokens, resuming within 24 hours, and Redis rate limits per token and per IP.
- Daily Token Budget, the "temporarily unavailable" state, an Agent alert badge, and an email to Owners.
- Operational Settings UI, applied immediately and audited (ADR-0009).
- Theme plus per-Agent overrides applied as CSS variables. Bubble and inline launchers. UI string overrides.
- WCAG 2.2 AA: keyboard navigation, focus trap, live region for streamed replies, axe in Playwright.
- Embed Snippet copy UI. Archived Agents show the "no longer available" shell.
- **Done when:** the seed host page embeds the Agent with the Theme applied, a page from a different origin cannot frame it, and exhausting the budget shows the friendly unavailable state.

### Slice 7: Feedback, logging and comparison
- Message Feedback (thumbs up or down plus a comment) and the Conversation Rating prompt (after the Nth reply and on "End chat"). Ratings can be edited, with changes logged.
- Conversation list and viewer in the Studio, with per-message Trace.
- Daily usage rollups (Celery Beat).
- Analytics: per-Version metrics with Wilson intervals and sample sizes. A side-by-side comparison of two Versions. A time series with markers where the Live pointer moved. Playground Conversations excluded.
- Retention Window purge job, and Traces keep a tombstone when a Document is deleted.
- **Done when:** seed data shows v2 against v3 with confidence intervals, and a purge removes expired Message text while the aggregates stay intact.

### Slice 8: Guardrails and evaluation
- Local ONNX prompt-injection classifier, plus an optional LLM classifier on the Agent's credential.
- Per-Agent block, warn or log mode. Canary token injection and the streaming-safe output filter.
- Guardrail outcomes shown in Traces and as an analytics metric (block rate).
- Attack evaluation suite: a versioned set of attack prompts with expected outcomes. Runs against the mocked model in CI and the real model nightly.
- **Done when:** the evaluation suite passes in CI, and the Trace for a jailbreak attempt shows which layer stopped it.

### Slice 9: Terraform and deploy
- Modules filled in:
  - Networking: VPC, subnets, `fck-nat` with a managed-NAT toggle.
  - Data: RDS with pgvector, ElastiCache, S3 buckets.
  - Compute: ECS cluster and three services, ALB locked to CloudFront.
  - Edge and secrets: CloudFront with path routing, KMS, Secrets Manager, ECR.
  - CI access: GitHub OIDC role.
- `envs/demo` root module, with remote state in S3 using native S3 state locking (`use_lockfile`).
- `terraform test` for module contracts. `deploy.yml` apply/destroy, with migrations run as a one-off ECS task.
- Optional `domain_name` variable adds Route 53 and ACM.
- **Done when:** `apply` brings up a working demo on `*.cloudfront.net`, and `destroy` removes all of it.

### Slice 10: Seed data and showcase
- `make seed`:
  - a demo Organisation with an Owner and an Editor;
  - a handbook and FAQ Project with Tags;
  - two Agents with three Versions of history, plus synthetic Conversations, feedback and ratings;
  - a host page with the embedded widget;
  - an attack panel page.
- README: pitch, architecture diagram, a five-minute demo script, the ADR index, how to run locally and how to deploy.
- **Done when:** a fresh clone, then `make dev && make seed`, gives the full interview demo in under five minutes.

---

## 8. Open items

- **Domain:** none yet. Running on the CloudFront default domain is fine. Revisit before SES email goes live in AWS.
- **AWS account / OIDC role:** CI can run without them. `plan` and deploy turn on once the secret exists.
- **Assumptions in section 3:** confirm or change before slice 5.
