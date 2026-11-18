# End-to-end coverage of the spec user stories

Every user story in `docs/specs/01`–`16` mapped against the Playwright suite in `frontend/e2e` (116 tests in 66 files), as of `main` at dd45d89.

## How to read this

- **Covered**: an e2e test drives the behaviour through the UI and asserts the outcome the story is about.
- **Partial**: an e2e test touches it but misses the part that matters (often the refusal, limit or expiry).
- **Gap**: user-facing behaviour no e2e test asserts. Severity is *high* for security, permissions, money or data loss, or a core flow; the note says when backend or frontend unit tests cover it instead.
- **Not e2e**: not an end-to-end concern (tooling, CI, Terraform, backend internals, model quality). The note says where it is checked.

Specs 15 (Live evaluation) and 16 (Suggestions) are not built yet, so their gaps are gaps by construction. They are counted separately below.

## Summary

698 stories. Across the 14 built specs, 289 of the 461 stories that belong in e2e are covered (63%), 83 partially and 89 not at all; 116 are not e2e concerns.

| Spec | Stories | Covered | Partial | Gap | Not e2e | Covered of e2e-able |
|---|--:|--:|--:|--:|--:|--:|
| [01](#spec-01) Spec 01: Skeleton, CI, auth and tenancy | 43 | 27 | 5 | 1 | 10 | 82% |
| [02](#spec-02) Spec 02: Provider Credentials and Theme | 33 | 26 | 5 | 2 | 0 | 79% |
| [03](#spec-03) Spec 03: Projects and Knowledge Base | 36 | 22 | 10 | 2 | 2 | 65% |
| [04](#spec-04) Spec 04: Agents, retrieval and Playground | 37 | 23 | 10 | 4 | 0 | 62% |
| [05](#spec-05) Spec 05: Versioning and Project Instructions | 34 | 25 | 4 | 2 | 3 | 81% |
| [06](#spec-06) Spec 06: Embed, widget and Operational Settings | 35 | 26 | 6 | 0 | 3 | 81% |
| [07](#spec-07) Spec 07: Feedback, logging and comparison | 33 | 25 | 4 | 1 | 3 | 83% |
| [08](#spec-08) Spec 08: Guardrails and evaluation | 25 | 14 | 2 | 2 | 7 | 78% |
| [09](#spec-09) Spec 09: Terraform and deploy | 34 | 0 | 0 | 0 | 34 | n/a |
| [10](#spec-10) Spec 10: Seed data and showcase | 25 | 12 | 1 | 2 | 10 | 80% |
| [11](#spec-11) Spec 11: Studio design system and reskin | 38 | 19 | 10 | 3 | 6 | 59% |
| [12](#spec-12) Spec 12: Reskin fixes and sidebar navigation | 83 | 40 | 13 | 25 | 5 | 51% |
| [13](#spec-13) Spec 13: Agentic retrieval | 45 | 18 | 5 | 5 | 17 | 64% |
| [14](#spec-14) Spec 14: Evaluation loop | 76 | 12 | 8 | 40 | 16 | 20% |
| [15](#spec-15) Spec 15: Live evaluation *(not built)* | 60 | 0 | 0 | 24 | 36 | 0% |
| [16](#spec-16) Spec 16: Suggestions *(not built)* | 61 | 0 | 0 | 36 | 25 | 0% |

## Patterns in the gaps

1. **The Editor's view is rarely tested end to end.** Most journeys run as an Owner. What an Editor sees or is refused (Cost in the sidebar and on the Cost page, Evaluation Model and repeats, archived Project settings) is tested only in backend and unit tests The exception is Members and Audit, which members.spec checks are hidden from an Editor and refused by the API (01.37, 01.41).
2. **Time-based rules have no e2e test.** Reset-link and invite expiry, the midnight budget reset and retention purges need a controllable clock. Backend tests have one; the e2e stack doesn't.
3. **Settings are changed, but their effect isn't checked.** Excluding flagged Chunks, the relevance threshold, deleting a Document and swapping an edition all change the UI, but no test then checks what retrieval returns.
4. **Failure and refusal paths.** Failed re-embeds, create and invite errors inside dialogs, the Document quota refusal, per-IP rate limits and the block-rate spike alert are only tested below e2e.
5. **Spec 14 (Evaluation loop) has one e2e journey.** evaluation-loop.spec.ts covers adding a case from a thumbs-down and seeing a Regression at Publish. Managing cases, choosing sides, Run cost and cancelling, Rollout evaluation and the Expected-source warnings are tested only with MSW and backend tests.
6. **Only the drawer gets keyboard and axe checks while open.** The New Project, Edit details and Invite dialogs, menus and switchers are left to Testing Library unit tests.

Severity was judged per spec by five separate reviewers using the same rubric, so treat it as a guide to ordering, not a precise score.

## Gaps that matter most (built specs)

High-severity gaps and partials first, then medium. Low-severity items are in the per-spec tables.

### High (2)

- **01.16** (high, gap) Repeated failed sign-ins slowed then locked out. No e2e lockout/throttle message. Covered at API seam: backend test_sign_in_throttling.py (13 tests).
- **14.71** (high, gap) Editors cannot change Evaluation Model/repeats. Permission; backend test_editors_cannot_change_the_evaluation_model_or_repeats + MSW, no e2e.

### Medium (58)

- **01.19** (medium, partial) Reset links expire and work only once. Single use asserted; expiry not (needs clock). Backend test_password_reset.py covers expiry.
- **01.20** (medium, partial) Resetting password ends other sessions. E2E proves change-password ends other sessions, not reset-link flow. Backend test_password_reset likely covers.
- **01.31** (medium, partial) Invites expire; Owner can revoke pending invite. Revoke covered (link then invalid); expiry not tested e2e. Backend test_invites.py covers expiry.
- **01.39** (medium, partial) Invites, roles, removals, MFA policy, security events audited. Invite/role/removal/leave/MFA-policy actions asserted; security events (failed sign-in, MFA enrol, password change) and before/after values mostly unchecked.
- **03.17** (medium, partial) Old edition serves until new one Ready. Only UI row state during processing; retrieval of old Chunks during swap not checked. Backend test_document_editions covers.
- **03.18** (medium, partial) Delete Document; stops being retrieved immediately. Delete UI covered; retrieval stop not asserted. Backend tests cover.
- **03.31** (medium, partial) Old vectors serve until re-embed completes, then switch. Probe checked before and after only, not during. Backend test_re_embedding covers.
- **03.32** (medium, gap) Failed re-embed stays on old model with error shown. No e2e failure path or error message. Backend test_re_embedding (provider failure partway) covers.
- **03.34** (medium, partial) Per-Project Document quota enforced with clear message. Quota '0 / 500' displayed; refusal at quota never triggered. Backend test_ingestion_failures covers.
- **04.13** (medium, gap) Set minimum relevance threshold. Only default 0 read; threshold effect/fallback not exercised. Backend test_retrieval covers.
- **05.6** (medium, gap) Choose a different Instructions Version when publishing. No test selects a non-current Instructions option (publishAgent's instructions arg unused). Backend test_agent_versions pins older version.
- **05.22** (medium, partial) Bulk publish builds from Live config, not Draft. Badge 'changes not included' shown, but no assertion B's bulk-published Version excludes its Draft edit. Backend test_bulk_versions covers.
- **05.24** (medium, gap) Never-published Agents excluded from bulk with explanation. No e2e with a never-published Agent in the rollout dialog. Backend test_bulk_versions skips_never_published covers.
- **06.8** (medium, partial) Per-Conversation and per-IP rate limits. Per-Conversation limit exercised end to end; per-IP only default value shown, never enforced. Backend test_rate_limits covers.
- **06.19** (medium, partial) Expandable citations showing Document name and passage. Widget reply shows 'Sources: northwind-staff-handbook.md'; expanding to the passage never asserted.
- **07.15** (medium, gap) Cost per Conversation per Version with frozen prices. No e2e asserts a cost KPI per Version or frozen-price behaviour. Backend test_version_metrics/test_prices and AnalyticsTab.test cover.
- **08.10** (medium, gap) Set the refusal text Visitors see. Only default 'Sorry, I can't help…' asserted; no test sets custom refusal text. Backend test_agent_config covers field.
- **08.14** (medium, partial) Per-Project: exclude flagged Chunks or only mark. Setting toggled to Exclude in UI, but effect on retrieval never asserted. Backend test_flagged_chunks covers.
- **08.19** (medium, gap) Alert badge when block rate spikes. No e2e triggers spike badge. Backend test_guardrail_analytics and AgentsTab.test.tsx cover the flag/badge.
- **11.7** (medium, partial) Switch Organisation/Project/section/Agent from its crumb. Superseded by sidebar switchers (spec 12). Org switch covered; switching to another Project or Agent (▾) not e2e.
- **11.24** (medium, partial) Allowed Origins editable list warns when empty. Add/remove/validate covered; empty-list warning never asserted.
- **11.32** (medium, partial) Switchers, menus, dialogs keyboard-operable and announced. Drawer keyboard path covered; menus/dialogs keyboard paths only in Testing Library unit tests.
- **12.19** (medium, gap) Create errors shown inside dialog, input kept. No e2e for create failure (e.g. duplicate/blank); unit seam.
- **12.28** (medium, gap) From and To date filters. Date filters never driven e2e; unit seam per spec.
- **12.33** (medium, gap) Error notice for bad dates (From>To, >366 days). 422 message covered only at network seam.
- **12.34** (medium, gap) Editor told only Owners see spend. Editor never visits Cost e2e; permission messaging unverified end to end.
- **12.40** (medium, gap) Invalid email / existing Member reported in dialog. No e2e for invite validation errors.
- **12.53** (medium, gap) Failed re-embed shown as error with reason. No failure path e2e.
- **12.57** (medium, gap) Archived Project settings shown disabled, no model change. No e2e; API refuses changes (409) per projects.spec for rename only.
- **12.63** (medium, gap) Editor's sidebar omits Cost. No e2e inspects an Editor's 'Organisation sections'; shell unit tests only.
- **12.73** (medium, gap) Switch Agent from ▾ on its name. Only harness/agent-navigation.spec.ts (fake page); no real-stack test.
- **12.83** (medium, partial) New dialogs and drawer pass axe in both Appearances. Drawer swept in both Appearances; New Project, Edit details and Invite dialogs not axe-scanned while open.
- **13.10** (medium, partial) Agentic Draft save refused when model lacks tools. Refusal (422, reason) asserted via API PUT only; UI showing server refusal not driven in e2e (MSW DraftEditor tests).
- **13.18** (medium, gap) Fallback Text when nothing relevant, in Agentic mode. No e2e Agentic reply with empty KB/fallback; backend API tests cover it.
- **14.2** (medium, gap) Write an Evaluation Case by hand. No e2e creates a case from the Evaluation view; AgentEvaluation.test.tsx (MSW).
- **14.4** (medium, gap) Set Expected source by choosing a Document passage. Source picker not driven in e2e; MSW + backend.
- **14.8** (medium, gap) Edit and delete cases. Delete only via API cleanup; no UI edit/delete.
- **14.10** (medium, gap) Copy cases from another Agent in Project. Backend + MSW only.
- **14.12** (medium, gap) Cases flagged with Stale expectation. No e2e makes a case stale or sees the flag.
- **14.16** (medium, gap) Same action on Playground answers. No e2e from Playground; MSW only.
- **14.18** (medium, gap) Cited passages offered as sources, unticked. Not asserted in e2e; MSW.
- **14.20** (medium, gap) Add-from-Message recorded as Audit Event. e2e checks source only, not audit; backend covers.
- **14.24** (medium, partial) Evaluate action in Evaluation view and Publish dialog. Publish dialog Evaluate driven; Evaluation view's Evaluate not.
- **14.26** (medium, gap) Choose any two sides (Draft or Version). Side pickers not driven; seeded v1-vs-v2 run only viewed.
- **14.31** (medium, gap) Estimated Cost shown before starting. Estimate not asserted in e2e; MSW + backend.
- **14.33** (medium, gap) Cancel a running Run. Backend task + MSW only.
- **14.38** (medium, gap) Each side's Evaluation score. No e2e asserts scores.
- **14.43** (medium, gap) Each answer with its Trace. Run detail Trace drawer not opened in e2e.
- **14.49** (medium, gap) Run Cost split answers vs judging. Backend cost + MSW only.
- **14.51** (medium, partial) Publish anyway after warning. Publish button enabled, never clicked.
- **14.55** (medium, gap) Rollout dialog offers Rollout evaluation. bulk-rollout e2e has no evaluation; RolloutEvaluation.test.tsx.
- **14.56** (medium, gap) Rollout lists Regressions, marks 'not evaluated'. MSW + backend test_evaluation_rollout.py.
- **14.58** (medium, gap) Warning before deleting Document with Expected source. documents e2e has no warning; MSW only.
- **14.59** (medium, gap) Same warning before new Edition upload. document-editions e2e has no warning.
- **14.62** (medium, gap) Owner chooses Evaluation Model in settings. models e2e doesn't touch it; backend + ModelsPage.test.tsx.
- **14.66** (medium, gap) Owner sets repeats 1/3/5/7/9. Backend + MSW only.
- **14.72** (medium, gap) Archived Agent keeps set/Runs, no new Run. agent-archive e2e ignores evaluation; backend covers.
- **14.76** (medium, partial) Evaluation UI fully accessible. axe on Evaluation view, Run detail, Publish dialog; case editor dialog not axe-checked, no keyboard flow.

## Specs 15 and 16: what e2e is planned

Not implemented: no Live Verdict, Live score, Evaluation budget, sample rate or Suggestions code in backend/app, frontend/apps or frontend/e2e (only Publish-summary 'Live Version' wording); all tickets 15-01..07 and 16-01..07 are ready-for-agent.

High-severity stories (16); the note says whether a ticket already plans an e2e test:

- **15.1** (high, gap) Set Agent Live sample rate 0-100% in Operational Settings. Not built yet. Planned in 15-07 (set HR helper rate to 100%).
- **15.22** (high, gap) Live Verdict with both checks and reasons in Trace. Not built yet. Planned in 15-07 (see Live Verdict in Conversations viewer Trace, axe on Trace section).
- **15.24** (high, gap) Filter Conversations viewer by Live Verdict. Not built yet. Planned in 15-07 (filter to failed replies).
- **15.26** (high, gap) Add failed reply to Evaluation Set. Not built yet. Planned in 15-07; reuses flow in evaluation-loop.spec.ts.
- **15.43** (high, gap) Owner sets monthly Evaluation budget in Org settings. Not built yet. 15-07 only axe-checks Org settings; no e2e of setting budget.
- **15.56** (high, gap) Editor cannot change Evaluation budget. Not built yet. API permission test + MSW read-only; no e2e planned.
- **16.1** (high, gap) Suggestions tab in Agent's Evaluation view. Not built yet. Planned in 16-07 (open seeded Suggestion; axe on Suggestions tab).
- **16.5** (high, gap) Estimated Cost shown before starting, proposing/checking split. Not built yet. MSW planned only; money-related.
- **16.19** (high, gap) System prompt change shown as line Diff. Not built yet. Planned in 16-07 (seeded Suggestion detail, apply).
- **16.30** (high, gap) Suggestion checked against Live on Evaluation Set. Not built yet. Planned in 16-07 (see seeded check).
- **16.37** (high, gap) Review Suggestion as Diff against current Draft. Not built yet. Planned in 16-07 (apply flow).
- **16.38** (high, gap) Applying writes all changes in one save. Not built yet. Planned in 16-07 (apply to Draft).
- **16.40** (high, gap) Apply refused on clashes, listing both values. Not built yet. API + MSW only; data-loss guard with no e2e.
- **16.41** (high, gap) Stale-Draft conflict offers Load theirs / Save mine. Not built yet. agent-drafts.spec.ts covers Draft editor conflict (16-01 prefactor must keep it passing); apply-flow conflict not in e2e.
- **16.44** (high, gap) Draft Evaluation summary asks for new Run after apply. Not built yet. Planned in 16-07 (Publish dialog asks for new Run).
- **16.55** (high, gap) Editor can start, cancel, apply, delete. Not built yet. 16-07 covers start and apply; cancel, delete and Editor role not.

## Stories by spec

<a id="spec-01"></a>
### 01 Spec 01: Skeleton, CI, auth and tenancy

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | One command starts the whole local stack | Not e2e | smoke › the System status page shows every service operational | Developer tooling (docker-compose). E2E suite runs on it implicitly; smoke.spec checks every service operational. |
| 2 | Single make entry point for dev/test/lint/e2e | Not e2e | – | Developer tooling; exercised by CI workflows, not testable via UI. |
| 3 | Config validated from env vars, fail fast | Not e2e | – | Backend-internal; backend/tests/integration/test_settings.py. |
| 4 | Frontend API client generated from OpenAPI | Not e2e | – | Dev tooling; backend test_openapi.py + frontend.yml api-client-drift job. |
| 5 | CI fails when generated client is stale | Not e2e | – | CI gate: .github/workflows/frontend.yml api-client-drift. |
| 6 | CI enforces 100% line+branch coverage | Not e2e | – | CI gate: backend.yml (fail_under=100) and frontend.yml coverage step. |
| 7 | CI runs lint, types, tests, audits, secret and image scans | Not e2e | – | CI gate: security.yml (gitleaks, pip-audit/pnpm audit, trivy), backend.yml, frontend.yml. |
| 8 | Terraform lint and policy checks from slice 1 | Not e2e | – | Infra CI: infra.yml (fmt, validate, tflint, checkov, terraform test). |
| 9 | Migrations tested by upgrade/downgrade round trip | Not e2e | – | backend test_migrations.py; backend.yml 'Alembic round trip'. |
| 10 | Telemetry scrubs Message text and secrets | Not e2e | – | Backend-internal; backend test_telemetry.py with in-memory exporter. |
| 11 | Visitor signs up with name, email, password, Organisation | Covered | auth › a visitor signs up, sees the signed-in shell and signs out | Sign-up form driven, lands on Projects with Organisation in sidebar. |
| 12 | Sign-up makes the Member Owner of a new Organisation | Covered | auth › a visitor signs up, sees the signed-in shell and signs out<br>members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends | Sign-up user reaches Settings; members.spec shows their role as owner and Owner-only tabs. |
| 13 | Member signs in with email and password | Covered | auth › a Member signs back in after a wrong password<br>password-reset › request a reset, open the email in Mailpit, set a new password and sign in | Sign in via form after wrong password, lands on Projects. |
| 14 | Session held in secure httpOnly cookie | Covered | auth › a visitor signs up, sees the signed-in shell and signs out | Asserts studio_session cookie httpOnly, secure, SameSite=Lax. |
| 15 | Member signs out | Covered | auth › a visitor signs up, sees the signed-in shell and signs out | Sign out returns to Sign in; replayed old cookie gets 401. |
| 16 | Repeated failed sign-ins slowed then locked out | Gap (high) | – | No e2e lockout/throttle message. Covered at API seam: backend test_sign_in_throttling.py (13 tests). |
| 17 | Sign-in errors don't reveal if email registered | Partial (low) | auth › a Member signs back in after a wrong password<br>password-reset › request a reset, open the email in Mailpit, set a new password and sign in | Generic 'Email or password is incorrect' and neutral reset message shown, but unregistered-email case not compared. Backend test_sign_in_and_out covers. |
| 18 | Request a password reset link by email | Covered | password-reset › request a reset, open the email in Mailpit, set a new password and sign in | Requests reset, opens Mailpit email, sets new password, signs in. |
| 19 | Reset links expire and work only once | Partial (medium) | password-reset › request a reset, open the email in Mailpit, set a new password and sign in | Single use asserted; expiry not (needs clock). Backend test_password_reset.py covers expiry. |
| 20 | Resetting password ends other sessions | Partial (medium) | password-reset › a Member renames themselves and changes their password, ending their other sessions | E2E proves change-password ends other sessions, not reset-link flow. Backend test_password_reset likely covers. |
| 21 | Enrol TOTP MFA via QR code | Covered | mfa › a Member enrols in MFA, signs in with a code and a recovery code, then turns MFA off | QR image shown, secret read, code confirms enrolment. |
| 22 | One-time recovery codes on MFA enrolment | Covered | mfa › a Member enrols in MFA, signs in with a code and a recovery code, then turns MFA off | 10 codes listed; one used to sign in; count drops to 9. |
| 23 | MFA code asked after password | Covered | mfa › a Member enrols in MFA, signs in with a code and a recovery code, then turns MFA off<br>mfa › a wrong code keeps the Member on the challenge | Password alone gives no session cookie; code required; wrong code refused. |
| 24 | Disable MFA needs password + code, unless Org requires | Covered | mfa › a Member enrols in MFA, signs in with a code and a recovery code, then turns MFA off<br>require-mfa › an Owner requires MFA, and an Editor is forced to enrol on their next visit | Wrong password refused, then turned off; refused while Org requires MFA. |
| 25 | Owner requires MFA for every Member | Covered | require-mfa › an Owner requires MFA, and an Editor is forced to enrol on their next visit | Owner toggles policy; audited as organisation.mfa_policy_changed. |
| 26 | Member guided to enrol when Org requires MFA | Covered | require-mfa › an Owner requires MFA, and an Editor is forced to enrol on their next visit | Editor sign-in lands on Security enrolment, other pages redirect, API 403 until enrolled. |
| 27 | Owner invites colleague by email with role | Covered | invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account | Invite email in Mailpit with subject/body; role Editor chosen. |
| 28 | Owner copies invite link instead of email | Covered | invites › an existing Member accepts a copied link, and a revoked link stops working<br>require-mfa › an Owner requires MFA, and an Editor is forced to enrol on their next visit | Email unchecked; link copied and used. |
| 29 | Invite link lets new person create account and join | Covered | invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account | Create account and join; signs in again later; link single-use. |
| 30 | Existing Member accepting invite adds Organisation | Covered | invites › an existing Member accepts a copied link, and a revoked link stops working | Colleague joins second Org; /me lists both Organisations. |
| 31 | Invites expire; Owner can revoke pending invite | Partial (medium) | invites › an existing Member accepts a copied link, and a revoked link stops working | Revoke covered (link then invalid); expiry not tested e2e. Backend test_invites.py covers expiry. |
| 32 | Organisation switcher for multi-Org Members | Covered | organisation-switcher › a Member of two Organisations switches between them, and the choice survives reloads and sign-ins | Switches Orgs; role-specific tabs; choice persists across reload and new sign-in. |
| 33 | Owner sees every Member with role | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends | Members table lists both with role selects. |
| 34 | Owner changes Member role Owner/Editor | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends | Promote then demote; Editor's tabs change; audited. |
| 35 | Owner removes Member, access ends immediately | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends | Removed Editor's next API call 404s and page shows not found. |
| 36 | Can't remove or demote the last Owner | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends<br>members › an Editor leaves, and the last Owner can't | Demote last Owner and last Owner leaving both refused with message. |
| 37 | Owner-only areas hidden from Editor and refused by API | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends<br>invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account<br>organisation-switcher › a Member of two Organisations switches between them, and the choice survives reloads and sign-ins | Members/Audit tabs hidden; API 403 on members and audit-events; direct URL shows 'Only Owners'. |
| 38 | Member leaves Organisation unless last Owner | Covered | members › an Editor leaves, and the last Owner can't | Editor leaves; last Owner refused; member.left audited. |
| 39 | Invites, roles, removals, MFA policy, security events audited | Partial (medium) | invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account<br>members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends<br>members › an Editor leaves, and the last Owner can't<br>require-mfa › an Owner requires MFA, and an Editor is forced to enrol on their next visit<br>audit › an Owner finds their Organisation's creation in the Audit tab | Invite/role/removal/leave/MFA-policy actions asserted; security events (failed sign-in, MFA enrol, password change) and before/after values mostly unchecked. |
| 40 | Audit tab filterable by actor, action, date | Covered | audit › an Owner finds their Organisation's creation in the Audit tab | Action, Actor and date filters applied; empty-state shown. |
| 41 | Audit tab hidden from Editors | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends | Editor's settings lack Audit; audit-events API returns 403. |
| 42 | Clean Studio shell with Projects and Org settings nav | Covered | auth › a visitor signs up, sees the signed-in shell and signs out<br>sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are<br>accessibility › every signed-in page has no WCAG 2.2 AA violations, in the light and the dark Appearance | Shell nav to Projects/Settings, sidebar navigation, axe sweep. |
| 43 | Edit profile name and change password | Covered | password-reset › a Member renames themselves and changes their password, ending their other sessions | Name saved and shown in banner; password changed. |

<a id="spec-02"></a>
### 02 Spec 02: Provider Credentials and Theme

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Owner adds Anthropic credential with API key | Covered | models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted<br>prices › an Owner sees the platform price table and overrides a price for one credential | Anthropic credential added through the form and checked. |
| 2 | Owner adds OpenAI credential | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown | OpenAI added via form; capabilities 'Chat, Embeddings' shown. |
| 3 | Owner adds Voyage credential | Covered | credentials › an Editor sees the Organisation's credentials but can't manage them<br>models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted<br>embedding-models › an Owner chooses a Voyage Embedding Model; the handbook embeds with it and its credential can't be deleted | Voyage added; 'Embeddings, Reranking' shown. |
| 4 | Bedrock credential via role ARN + external ID | Covered | bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | Role ARN saved after check; no secret stored. |
| 5 | Studio shows external ID and trust policy | Covered | bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | External ID format, trust policy JSON with matching ExternalId, permissions policy; stable across reload. |
| 6 | Bedrock access key fallback | Covered | bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | Access keys saved, masked suffix shown. |
| 7 | Credential checked live on save | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | Bad key not saved; good key 'checked and saved' (fake verifier). |
| 8 | Clear reason when check fails | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | Invalid key, role not assumable, wrong region reasons shown; 'missing model access' reason not exercised. |
| 9 | Name each credential | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown | Named credentials listed by name. |
| 10 | See provider, capabilities, masked suffix, last-checked | Partial (low) | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>credentials › an Editor sees the Organisation's credentials but can't manage them | Provider, capabilities, ••••suffix and 'Working' asserted; last-checked time not asserted. |
| 11 | Re-run check on demand | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | 'Check now' passes. |
| 12 | Rotate secret keeping identity | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown | Rotated suffix shown; first cell unchanged; credential.rotated audited. |
| 13 | Delete credential, told which Agents/Projects reference it | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted<br>embedding-models › an Owner chooses a Voyage Embedding Model; the handbook embeds with it and its credential can't be deleted<br>agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override | UI names Default Model and Project references; Agent model/reranker references asserted via API 409 body. |
| 14 | Deletion blocked while referenced | Covered | models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted<br>embedding-models › an Owner chooses a Voyage Embedding Model; the handbook embeds with it and its credential can't be deleted | Delete refused; row remains. |
| 15 | API never returns secret after save | Covered | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>bedrock-credentials › an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys | Credentials list and audit API bodies lack key. Also backend test_no_secret_in_responses.py. |
| 16 | Editor sees credentials without managing | Covered | credentials › an Editor sees the Organisation's credentials but can't manage them | Editor sees row, suffix, capabilities; no add form or delete. |
| 17 | Owner sets Default Model from chat credential | Covered | models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted | Saved, persisted across reload, audited. |
| 18 | Model list limited by capability | Covered | models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted | Only chat-capable credential offered, with its chat models. |
| 19 | See platform price per model | Covered | prices › an Owner sees the platform price table and overrides a price for one credential | Price table row shows $3.00/$15.00/$0.30. |
| 20 | Override prices per credential | Covered | prices › an Owner sees the platform price table and overrides a price for one credential | Input override saved, persisted, audited, reverted. |
| 21 | Credential/Default Model/price changes audited without secret | Partial (low) | credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted<br>prices › an Owner sees the platform price table and overrides a price for one credential | created/rotated/check_failed/default_model/price_overridden asserted; credential.deleted not asserted. |
| 22 | Set Theme primary, surface, text, accent colours | Partial (low) | theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves<br>branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Primary and text-on-primary edited in UI; surface/accent never edited. |
| 23 | Set corner radius | Gap (low) | – | Radius never edited in e2e. Frontend ThemePage.test.tsx / backend test_theme likely cover. |
| 24 | Choose font from curated list | Gap (low) | – | Font picker not exercised e2e. Lower-level ThemePage/theme tests. |
| 25 | Upload logo and default avatar | Covered | theme › an Owner uploads, replaces and removes the logo and avatar, and the preview shows them<br>theme › an Editor sees the Theme's images but can't upload or remove them | Upload, replace, remove; preview loads images; bad type refused; audited. |
| 26 | Choose light, dark or automatic mode | Partial (low) | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Mode set to auto via API; widget follows dark/light. Mode radio in Theme editor never driven. |
| 27 | Choose bubble or inline launcher, and bubble corner | Partial (low) | theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves<br>branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Corner chosen in UI and persisted; inline vs bubble only via snippet query param, Theme 'Launcher' option not driven. |
| 28 | Live preview while editing Theme | Covered | theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves | Preview CSS var and painted colour update before save. |
| 29 | WCAG AA contrast warning | Covered | theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves | Warning appears with ratio, disappears when fixed. |
| 30 | Theme changes apply on save without publishing | Covered | theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves<br>branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | 'Widget uses it now'; reload shows; widget reflects Theme/Agent colour without republish. |
| 31 | Theme changes audited | Covered | theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves<br>theme › an Owner uploads, replaces and removes the logo and avatar, and the preview shows them | theme.updated rows with changed values. |
| 32 | Editor views Theme but can't change | Covered | theme › an Editor views the Theme and its preview but can't change it<br>theme › an Editor sees the Theme's images but can't upload or remove them | Disabled inputs, no Save; API PUT/upload 403. |
| 33 | Credentials, Default Model, Theme pages clean and clear | Covered | accessibility › every signed-in page has no WCAG 2.2 AA violations, in the light and the dark Appearance<br>credentials › an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown<br>models › an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted<br>theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves | Axe checks on each page; subjective 'self-explanatory' not testable beyond that. |

<a id="spec-03"></a>
### 03 Spec 03: Projects and Knowledge Base

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Create Project with name and description | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>projects › an Editor creates and archives a Project but only an Owner restores it | New Project form; heading shown. |
| 2 | Projects strictly isolated from each other | Not e2e | – | Backend guarantee; backend test_tenant_isolation.py project isolation suite, test_tags cross-project. |
| 3 | List active Projects with Document and Agent counts | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>documents › an Owner uploads the seed handbook and it goes from Queued to Ready | Row shows counts 0/0; Document count 1 after upload. |
| 4 | Rename Project and edit description | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Edit details saves name and description. |
| 5 | Archive Project: leaves list, stops serving | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>projects › an Editor creates and archives a Project but only an Owner restores it | Leaves Active list; PATCH refused 409; 'stops serving' widget not checked. |
| 6 | Owner restores archived Project | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>projects › an Editor creates and archives a Project but only an Owner restores it | Owner restores; Editor sees no Restore and API 403. |
| 7 | Owner permanently deletes archived Project after typing name | Covered | project-deletion › an Owner deletes an archived Project after typing its name, and its stored files go too | Name must match exactly; Project and stored file 404; project.deleted audited. |
| 8 | Drag and drop several files at once | Partial (low) | tags › an Editor organises Documents with Tags and filters the list by name, status and Tag | Multiple files uploaded via file input; drag-and-drop dropzone never exercised. |
| 9 | Supported types accepted, others refused clearly | Covered | ingestion-failures › an unsupported file is refused before upload, and a broken one fails with its category and can be retried | xlsx refused with clear message; md/txt/pdf accepted. |
| 10 | Oversized files refused before upload | Gap (low) | – | No e2e for size limit. Frontend DocumentsTab tests and backend test_ingestion_failures (upload limits) cover. |
| 11 | Per-file upload progress bar | Partial (low) | documents › an Owner uploads the seed handbook and it goes from Queued to Ready | Only the 'Uploaded' status in the Uploads list asserted; no progress bar. |
| 12 | Document status shown and updated without refresh | Covered | documents › an Owner uploads the seed handbook and it goes from Queued to Ready<br>ingestion-failures › an unsupported file is refused before upload, and a broken one fails with its category and can be retried | Polls to Ready without reload; failure category shown. |
| 13 | Readable error when Document fails | Covered | ingestion-failures › an unsupported file is refused before upload, and a broken one fails with its category and can be retried | 'Unsupported content' with explanatory message. |
| 14 | Retry a failed Document | Covered | ingestion-failures › an unsupported file is refused before upload, and a broken one fails with its category and can be retried | Retry re-processes; toast shown. |
| 15 | Identical upload refused as duplicate with link | Covered | document-editions › a duplicate is refused, a new edition replaces the Document in place, and delete removes it | Refusal names existing Document; link navigates to it. |
| 16 | New edition replaces Document in place | Covered | document-editions › a duplicate is refused, a new edition replaces the Document in place, and delete removes it | Row count unchanged, new name Ready. Tags/history retention not asserted. |
| 17 | Old edition serves until new one Ready | Partial (medium) | document-editions › a duplicate is refused, a new edition replaces the Document in place, and delete removes it | Only UI row state during processing; retrieval of old Chunks during swap not checked. Backend test_document_editions covers. |
| 18 | Delete Document; stops being retrieved immediately | Partial (medium) | document-editions › a duplicate is refused, a new edition replaces the Document in place, and delete removes it | Delete UI covered; retrieval stop not asserted. Backend tests cover. |
| 19 | Filter/search Documents by name, status, Tag | Covered | tags › an Editor organises Documents with Tags and filters the list by name, status and Tag | Tag filter, name search, status filter, clear filters. |
| 20 | Create, rename, delete Tags | Covered | tags › an Editor organises Documents with Tags and filters the list by name, status and Tag | All three plus duplicate-name refusal. |
| 21 | Several Tags per Document and bulk tagging | Covered | tags › an Editor organises Documents with Tags and filters the list by name, status and Tag | Two Tags on one Doc; bulk Add Tag to two Docs. |
| 22 | View converted markdown of a Document | Covered | documents › an Owner opens the handbook in the Document viewer and downloads the original | Converted markdown region with heading. |
| 23 | Chunks shown with heading context and page numbers | Partial (low) | documents › an Owner opens the handbook in the Document viewer and downloads the original | Heading path asserted; page numbers never (markdown fixture has no pages). |
| 24 | Instruction-like Chunks flagged with reason | Covered | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it | Planted Chunk flagged with reason and score; clean Chunk not. |
| 25 | Flagged Chunk count per Document in list | Covered | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it | Flagged column shows 1. |
| 26 | Download original file | Covered | documents › an Owner opens the handbook in the Document viewer and downloads the original | Download matches original bytes. |
| 27 | Turn on OCR per Project | Partial (low) | ocr › an Owner turns OCR on for a Project and reprocesses a Document with it through retry | Toggle saved and retry runs; no scanned PDF proves OCR text extracted. |
| 28 | New Projects use local Embedding Model by default | Covered | embedding-models › an Owner chooses a Voyage Embedding Model; the handbook embeds with it and its credential can't be deleted<br>embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over | Settings show multilingual-e5-small; probe confirms. |
| 29 | Choose Voyage/OpenAI/Bedrock Embedding Model | Covered | embedding-models › an Owner chooses a Voyage Embedding Model; the handbook embeds with it and its credential can't be deleted | Voyage chosen and used (probe dim 1024); OpenAI/Bedrock not exercised. |
| 30 | Changing model re-embeds in background with visible progress | Partial (low) | embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over | Switch completes; progress UI during the job not asserted. |
| 31 | Old vectors serve until re-embed completes, then switch | Partial (medium) | embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over | Probe checked before and after only, not during. Backend test_re_embedding covers. |
| 32 | Failed re-embed stays on old model with error shown | Gap (medium) | – | No e2e failure path or error message. Backend test_re_embedding (provider failure partway) covers. |
| 33 | Uploads during re-embed embedded with both models | Not e2e | – | Backend-internal guarantee; backend test_re_embedding 'uploaded_during_the_job_are_embedded_with_both_models'. |
| 34 | Per-Project Document quota enforced with clear message | Partial (medium) | ingestion-failures › an unsupported file is refused before upload, and a broken one fails with its category and can be retried | Quota '0 / 500' displayed; refusal at quota never triggered. Backend test_ingestion_failures covers. |
| 35 | Project/Embedding/Document-delete changes audited | Partial (low) | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>project-deletion › an Owner deletes an archived Project after typing its name, and its stored files go too<br>embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over | project created/archived/restored/deleted and re_embed_started asserted; Document delete audit not. |
| 36 | Project page tabs: Documents, Instructions, Agents, Conversations, Analytics | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Each tab opened and heading checked. |

<a id="spec-04"></a>
### 04 Spec 04: Agents, retrieval and Playground

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Create Agent in Project with a name | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>agent-archive › an Owner archives an Agent, restores it, then deletes it permanently after typing its name | New Agent form; Agent page heading. |
| 2 | Several Agents per Project | Covered | agent-archive › an Owner archives an Agent, restores it, then deletes it permanently after typing its name | Two Agents created in one Project and listed. |
| 3 | See Project's Agents with status | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-archive › an Owner archives an Agent, restores it, then deletes it permanently after typing its name | Agents table shows 'Not live'/'Live v1'; archived list separate. |
| 4 | Edit system prompt in markdown editor | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | System prompt contenteditable filled and autosaved; persists after reload. |
| 5 | Editor stores markdown and round-trips exactly | Partial (low) | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>instructions › an Owner formats Instructions in the markdown editor and the markdown is saved and audited | Exact markdown round-trip proven for Project Instructions; system prompt only plain text. Frontend markdown fixture tests cover. |
| 6 | Agent uses Org Default Model unless overridden | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Reply from anthropic:claude-haiku-4-5 (Default Model). |
| 7 | Override model with chat credential and model | Covered | agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override | OpenAI GPT-4.1 mini chosen; Playground answers with it; persists. |
| 8 | Set temperature and max output tokens | Partial (low) | agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override | Temperature set and validated; max output tokens never set. DraftEditor.test covers. |
| 9 | Choose how many previous turns remembered | Gap (low) | – | Remembered turns not exercised e2e. DraftEditor.test.tsx and backend test_playground cover. |
| 10 | Set fallback text when nothing relevant | Partial (low) | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Default fallback text appears (canary/no-docs cases); custom fallback text never set via editor. |
| 11 | Set how many Chunks retrieved (top-k) | Covered | reranker › an Editor turns on a reranker and the best Chunk rises to the top | top-k=1; Trace shows second Chunk left out. |
| 12 | Adjust semantic vs keyword balance | Gap (low) | – | Hybrid weighting never touched e2e. Backend test_retrieval (keyword/hybrid weighting) covers. |
| 13 | Set minimum relevance threshold | Gap (medium) | reranker › an Editor turns on a reranker and the best Chunk rises to the top | Only default 0 read; threshold effect/fallback not exercised. Backend test_retrieval covers. |
| 14 | Limit Agent to Documents with certain Tags | Covered | tag-scoping › an Agent limited to a Tag is given only that material, and deleting the Tag warns which Agents use it | Tag scoping via UI; only HR Doc cited; other excluded in Trace. |
| 15 | Turn on reranker with Voyage/Bedrock | Covered | reranker › an Editor turns on a reranker and the best Chunk rises to the top | Voyage reranker chosen; reranked Chunk first with score. |
| 16 | Choose whether citations shown to Visitors | Gap (low) | – | No e2e toggles citations or checks widget hides/shows them. |
| 17 | Set display name, avatar, greeting, starter questions | Partial (low) | agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override<br>branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Greeting set in UI; display name/starters set via API and shown in widget; Agent avatar not tested. |
| 18 | Override widget built-in text | Partial (low) | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark<br>operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | send_button override set via API and shown; unavailable text worded in UI (operational settings); editor UI for overrides not driven. |
| 19 | Choose after how many replies to ask for rating | Partial (low) | conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating | rating_prompt_after=1 set via API; widget asks after first reply. Editor field not driven. |
| 20 | Set Guardrail mode and optional LLM classifier | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override<br>llm-classifier › an Agent's LLM classifier refuses what it flags, and its fail mode decides an outage | Block/warn/log modes switched in UI with effects; classifier configured (API) and fail mode in UI. |
| 21 | Validation explains invalid settings | Covered | agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override<br>playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search | Out-of-range temperature and Search limit flagged; tool-incapable model 422 via API. Credential/model mismatch not via UI. |
| 22 | Draft autosaves and shows unpublished changes | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override<br>agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | 'All changes saved' status; Draft vs Live diff reviewed in agent-drafts. |
| 23 | Edit Project Instructions as markdown | Covered | instructions › an Owner formats Instructions in the markdown editor and the markdown is saved and audited | Toolbar formatting, exact markdown saved, audited. |
| 24 | Chat with Draft in Playground | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override | Question sent, Draft answers. |
| 25 | Playground answers stream token by token | Partial (low) | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search | Only final text asserted (plus injected retract event); incremental rendering not checked. Frontend MSW streaming test covers. |
| 26 | Playground citations link to Document and Chunk | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Source chip href to document viewer #chunk-. |
| 27 | Open Trace: model, tokens, cost, latency, Chunks, cited, Guardrails | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search | All listed Trace fields asserted. |
| 28 | See Chunks filtered by threshold or Tags | Partial (low) | tag-scoping › an Agent limited to a Tag is given only that material, and deleting the Tag warns which Agents use it<br>reranker › an Editor turns on a reranker and the best Chunk rises to the top | Tag exclusion and top-k left-out shown; threshold-filtered Chunks not. |
| 29 | Reset Playground Conversation | Covered | playground-errors › a provider failure is explained, and a reset starts a new Conversation | New empty Conversation; next question goes to it. |
| 30 | Change Draft and immediately re-ask | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Guardrail mode changed then re-asked with different outcome. |
| 31 | Playground excluded from metrics and Token Budget | Covered | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count<br>token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers<br>conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace | KPIs ignore Playground; Playground answers after budget spent; flagged in Conversations. |
| 32 | Playground usage counts toward cost reporting | Partial (low) | organisation-cost › an Owner opens the Cost page from the navigation and sees each Project's and Agent's cost, the Playground in its own column | Cost page has a Playground column, but Playground message sent via API and its amount not asserted. |
| 33 | Clear Playground error on provider failure | Covered | playground-errors › a provider failure is explained, and a reset starts a new Conversation | Rate limit, invalid key, model unavailable each show readable alert. |
| 34 | Archive an Agent | Covered | agent-archive › an Owner archives an Agent, restores it, then deletes it permanently after typing its name | Archived: read-only, Playground gone, archived list. |
| 35 | Owner permanently deletes archived Agent after typing name | Covered | agent-archive › an Owner archives an Agent, restores it, then deletes it permanently after typing its name | Exact name required; deleted. Editor refusal not tested. |
| 36 | Agent create/archive/restore/delete and Instructions edits audited | Partial (low) | agent-archive › an Owner archives an Agent, restores it, then deletes it permanently after typing its name<br>instructions › an Owner formats Instructions in the markdown editor and the markdown is saved and audited | archive/restore/delete and instructions_updated asserted; agent.created not. |
| 37 | Model, reranker, classifier credentials registered as references | Covered | agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override<br>reranker › an Editor turns on a reranker and the best Chunk rises to the top | Model and reranker credentials 409 with references; classifier reference not asserted. |

<a id="spec-05"></a>
### 05 Spec 05: Versioning and Project Instructions

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Publish Draft as new numbered Version | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log | Publish dialog → 'Published v1 … It is now Live'; API confirms v1. |
| 2 | Add a note when publishing | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>instructions-versions › an Owner publishes the Instructions twice with notes, browses the history and reverts, all audited | Note filled in dialog; API versions list and audit after.live_version.note assert 'First release'. |
| 3 | Publishing makes new Version Live immediately | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log | Live chip v1, 'Not live' gone, Agent list shows 'Live v1', live_version_id matches. |
| 4 | Each Agent Version pins an Instructions Version | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log<br>bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Status 'with Instructions v1'; API instructions_version.number asserted; revert restores pinned Instructions. |
| 5 | New Versions pin Current Instructions by default | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log | Picker defaults to 'Current Version (vN)' and publish reports Instructions vN. |
| 6 | Choose a different Instructions Version when publishing | Gap (medium) | – | No test selects a non-current Instructions option (publishAgent's instructions arg unused). Backend test_agent_versions pins older version. |
| 7 | Versions are immutable | Not e2e | – | Backend-internal guarantee: backend/tests/integration/test_agent_versions.py test_versions_cannot_be_changed_through_the_api. |
| 8 | Version list shows number, author, time, note, pinned Instructions, Live | Partial (low) | agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log<br>agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | Versions view used (row actions, Live chip) but author/time/note/pinned-Instructions columns of the list never asserted in UI. |
| 9 | Live History: every Live change, by whom, publish vs revert | Covered | agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log<br>five-minute-demo › the five-minute demo | Timeline 'Published v1 → v2', 'Reverted v2 → v1' asserted; actor ('by whom') not asserted. |
| 10 | Compare any two Versions as a field diff | Covered | agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | Compare From v1 To v2 shows system-prompt line diff; pinned-Instructions part of diff not asserted. |
| 11 | Compare Draft against Live Version | Covered | agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | Publish dialog 'Changes to publish' shows prompt diff and Retrieval mode/limit changes. |
| 12 | Revert to previously Live Version, restoring Instructions | Covered | agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log<br>bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Confirm dialog, 'Reverted to v1 with Instructions v1', API live=[1,1], audit agent.reverted. |
| 13 | Revert follows Live History, skipping reverted Version | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Agent A history publish→bulk_publish→bulk_revert→bulk_publish; final revert from v3 lands on v1 (skips v2), via API check. |
| 14 | Told when there's nothing to revert to | Covered | agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log | 'There's no earlier Live Version to revert to: v1 was the first.' shown; API revert 409. |
| 15 | Start new Draft from any past Version | Covered | agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | 'Start Draft from v1' menu + confirm; Draft badge appears, v2 stays Live; audited. |
| 16 | 'Unpublished changes' indicator when Draft differs | Covered | agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | Draft badge visible after edit, gone after discard. |
| 17 | Discard Draft back to Live Version | Covered | agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | Discard confirm; badge gone; v2 prompt back; publish dialog shows no differences; audited. |
| 18 | Never-published Agent clearly 'not live' | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log | 'Not live' + 'Visitors can't use it until you publish it.'; Versions view empty-state text. |
| 19 | Publish Project Instructions as new Current Version | Covered | instructions-versions › an Owner publishes the Instructions twice with notes, browses the history and reverts, all audited<br>bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Publish twice; 'Current Version: v2.'; API current_version_id; audited. |
| 20 | Instructions publish opens bulk dialog with Agents pre-selected | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | 'Roll out Instructions v2' dialog with Agent A and B checkboxes checked. |
| 21 | Deselect Agents in bulk dialog | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Agent B unchecked; 'Publish to 1 Agent'; B stays on v1. |
| 22 | Bulk publish builds from Live config, not Draft | Partial (medium) | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Badge 'changes not included' shown, but no assertion B's bulk-published Version excludes its Draft edit. Backend test_bulk_versions covers. |
| 23 | Badge Agents with unpublished Draft in bulk dialog | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Agent B row shows 'Draft' badge and 'changes not included'. |
| 24 | Never-published Agents excluded from bulk with explanation | Gap (medium) | – | No e2e with a never-published Agent in the rollout dialog. Backend test_bulk_versions skips_never_published covers. |
| 25 | Bulk results per Agent: succeeded/skipped/failed | Partial (low) | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Only 'Done' outcomes asserted; skipped and failed result rendering untested e2e. Backend test_bulk_versions + frontend unit tests. |
| 26 | Bulk action one transaction per Agent | Not e2e | – | Backend guarantee: test_bulk_versions.py test_a_failure_on_one_agent_leaves_the_others_committed. |
| 27 | Revert Instructions, then offered bulk revert of pinned Agents | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions<br>instructions-versions › an Owner publishes the Instructions twice with notes, browses the history and reverts, all audited | Revert to v1 opens 'Revert the Agents on Instructions v2?' with both checked; Revert 2 Agents; API live [1,1]. |
| 28 | Multi-select Agents in list and revert together | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | Agent list checkbox + Bulk actions Revert; result 'Reverted to v1 with Instructions v1'. |
| 29 | 'N Agents behind' and per-Agent pinned Instructions | Covered | bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions | '1 Agent behind the Current Version v2'; table rows 'v2v2' and 'v1Instructions behind'. |
| 30 | Instructions Version history with diffs | Partial (low) | instructions-versions › an Owner publishes the Instructions twice with notes, browses the history and reverts, all audited | History list, notes, Current badge and 'Show the Instructions' asserted; diff only shows 'No differences' — no real version-to-version diff. |
| 31 | Pick Instructions Version in Playground, default Draft | Covered | playground-instructions › an Owner asks the Agent's Draft with the Instructions Draft, then with a Version, and each answer records which | Picker defaults to Instructions Draft; answers/Trace show 'Instructions: Draft' then v1; API records source. |
| 32 | Every Message records producing Agent Version or Draft | Covered | playground-instructions › an Owner asks the Agent's Draft with the Instructions Draft, then with a Version, and each answer records which<br>conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace<br>message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer | Playground records draft/version; Visitor reply shows 'Version 1', Trace 'Pinned by Agent Version v1'. |
| 33 | Publish/revert/bulk actions recorded as Audit Events | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log<br>agent-revert › an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log<br>bulk-rollout › an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions<br>instructions-versions › an Owner publishes the Instructions twice with notes, browses the history and reverts, all audited<br>agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save | API audit queries for agent.published, agent.reverted, project.agents_bulk_published, instructions_published/reverted, draft actions. |
| 34 | Concurrent publishes give distinct Versions or clear conflict | Not e2e | – | Concurrency: backend test_agent_versions.py test_concurrent_publishes_get_consecutive_unique_numbers. (e2e covers Draft-save 409 only.) |

<a id="spec-06"></a>
### 06 Spec 06: Embed, widget and Operational Settings

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Copy Agent's Embed Snippet from Studio | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version | Copy button; clipboard content equals snippet; 'Copied'. |
| 2 | Snippet supports launcher type and inline container attributes | Partial (low) | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Snippet asserted without attributes; layouts driven by host-page query params, not snippet attrs from Studio. Unit AgentEmbed.test/embed.test cover. |
| 3 | Snippet unavailable until Agent has Live Version | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version | 'Publish the Agent to get its Embed Snippet.' and no Copy button before publish. |
| 4 | Manage Allowed Origins list | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | Add, remove, save origins; CSP frame-ancestors reflects list. |
| 5 | Allowed Origins validated (scheme/host/port/wildcard) | Covered | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | 'www.example.com' refused with message; port origin and https://*.example.com accepted. |
| 6 | Localhost origins allowed for development | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | Host origin is http://localhost:5175 and is saved and allowed to frame the widget. |
| 7 | Allowed Origins changes apply immediately without publishing | Covered | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | Live stays v1 after save; CSP updated and Visitor sees widget at once. |
| 8 | Per-Conversation and per-IP rate limits | Partial (medium) | rate-limits › an Editor limits each Conversation to one message a minute; a Visitor's second message gets the unavailable text, and the Playground is exempt | Per-Conversation limit exercised end to end; per-IP only default value shown, never enforced. Backend test_rate_limits covers. |
| 9 | Set daily Token Budget per Agent | Covered | token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers | Budget set to 1; next Visitor message gets unavailable event reason budget_exhausted. |
| 10 | See today's token use vs budget | Covered | token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers | '0 of 1 tokens used today (0%)' and meter aria-valuenow 1 after spend. |
| 11 | Set 'temporarily unavailable' text | Covered | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget<br>rate-limits › an Editor limits each Conversation to one message a minute; a Visitor's second message gets the unavailable text, and the Playground is exempt<br>token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers | Custom text saved and shown to Visitor in widget. |
| 12 | Operational Settings changes audited with before/after | Covered | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | Audit events agent.operational_settings_changed with exact before/after for origins and unavailable text. |
| 13 | Owner overrides Theme colours and avatar per Agent | Partial (low) | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Per-Agent primary colour override saved and applied in widget; avatar override not exercised. |
| 14 | Launcher bubble opens chat | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark<br>widget-accessibility › a keyboard and screen-reader Visitor uses the bubble in {light,dark} mode (…motion), and axe finds no AA violations<br>demo-pages › the shop page on the allowed origin shows the Product FAQ as a bubble, and a Visitor chats with it | 'Open chat' bubble 88px, opens to 420px panel. |
| 15 | Inline layout fits host container | Covered | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark<br>demo-pages › the help-centre page shows the same Agent inline | Inline iframe in host region 560px high, no launcher. |
| 16 | Widget matches site colours, font, logo, light/dark | Partial (low) | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark<br>widget-accessibility › a keyboard and screen-reader Visitor uses the bubble in {light,dark} mode (…motion), and axe finds no AA violations | Theme CSS vars for primary/surface in light and dark asserted; font and logo in widget not asserted. |
| 17 | See greeting and starter questions | Covered | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | Greeting text and starter question button that asks itself. |
| 18 | Replies stream in | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>widget-accessibility › a keyboard and screen-reader Visitor uses the bubble in {light,dark} mode (…motion), and axe finds no AA violations | Responses are text/event-stream; searching status then answer rendered progressively. |
| 19 | Expandable citations showing Document name and passage | Partial (medium) | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version | Widget reply shows 'Sources: northwind-staff-handbook.md'; expanding to the passage never asserted. |
| 20 | Conversation persists across reload within 24h | Covered | widget-lifecycle › a Visitor's Conversation comes back after a reload; New chat and End chat start afresh; a retired Agent says so | Reload restores messages and continues. 24h expiry refusal is backend (test_widget_resume). |
| 21 | Start a new Conversation | Covered | widget-lifecycle › a Visitor's Conversation comes back after a reload; New chat and End chat start afresh; a retired Agent says so | New chat clears log; reload doesn't restore old one. |
| 22 | End the chat | Covered | widget-lifecycle › a Visitor's Conversation comes back after a reload; New chat and End chat start afresh; a retired Agent says so<br>conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating | End chat → 'You ended the chat.', input gone; reload starts fresh. |
| 23 | Polite on-brand message when unavailable | Covered | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget<br>rate-limits › an Editor limits each Conversation to one message a minute; a Visitor's second message gets the unavailable text, and the Playground is exempt<br>token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers<br>demo-pages › one click spends the Low-budget helper's Token Budget: the widget shows its unavailable text and the Studio its alert | Custom unavailable text shown as alert instead of error. |
| 24 | Friendly message when Agent retired | Covered | widget-lifecycle › a Visitor's Conversation comes back after a reload; New chat and End chat start afresh; a retired Agent says so<br>widget-lifecycle › an Agent that was never published shows the no longer available shell on the host page | Archive mid-Conversation → 'This assistant is no longer available.'; never-published shows it too. |
| 25 | Keyboard: open/use/close, focus trap, focus returned | Covered | widget-accessibility › a keyboard and screen-reader Visitor uses the bubble in {light,dark} mode (…motion), and axe finds no AA violations | Tab to launcher, Enter opens, Tab cycles inside, Escape closes and refocuses launcher. |
| 26 | Screen reader: polite announcements, labelled controls | Covered | widget-accessibility › a keyboard and screen-reader Visitor uses the bubble in {light,dark} mode (…motion), and axe finds no AA violations<br>widget-accessibility › axe finds no AA violations on the inline widget in light and dark mode | Announcements status gets full reply once complete; axe clean open/closed. |
| 27 | Respect reduced motion | Covered | widget-accessibility › a keyboard and screen-reader Visitor uses the bubble in {light,dark} mode (…motion), and axe finds no AA violations | Panel animation 'none' with reduced motion vs 'widget-open'. |
| 28 | Phone: widget fills screen when open | Covered | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark | 390x844 viewport → iframe 390x844 when open. |
| 29 | Embed script small, async, no global side effects | Not e2e | – | CI 'Embed loader size budget' (frontend.yml check-embed-size) and apps/widget/src/embed.test.ts. |
| 30 | Widget styles/scripts isolated from host page | Not e2e | – | Architectural (iframe); loader unit tests in apps/widget/src/embed.test.ts. |
| 31 | Studio alert badge on budget exhausted or heavy limiting | Partial (low) | token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers<br>demo-pages › one click spends the Low-budget helper's Token Budget: the widget shows its unavailable text and the Studio its alert<br>five-minute-demo › the five-minute demo | 'Budget spent' badge on Agent page and list asserted; badge for heavy rate-limit hits not tested. |
| 32 | Owner emailed when Token Budget exhausted | Covered | token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers | Mailpit email subject 'Thrifty helper has used its daily Token Budget', mentions midnight UTC. |
| 33 | Token Budget resets at midnight UTC | Not e2e | – | Needs controllable clock: backend test_token_budget.py test_the_budget_resets_at_midnight_utc…. |
| 34 | Playground excluded from Token Budget | Covered | token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers<br>rate-limits › an Editor limits each Conversation to one message a minute; a Visitor's second message gets the unavailable text, and the Playground is exempt | After budget spent, Playground still answers. |
| 35 | Non-allowed origin can't show the Agent | Covered | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget<br>demo-pages › a page on a disallowed origin pastes the same snippet, and the browser refuses to show the widget<br>five-minute-demo › the five-minute demo | Browser frame-ancestors refusal in console / chrome-error frame; widget content absent. |

<a id="spec-07"></a>
### 07 Spec 07: Feedback, logging and comparison

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Thumbs up/down on any reply | Covered | message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer<br>version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | aria-pressed toggles; feedback visible in Studio. |
| 2 | Optional comment on thumbs down | Covered | message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer | Comment saved, shown in widget and in Studio Conversation feedback. |
| 3 | Change or remove thumbs | Partial (low) | message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer | Change up→down asserted; removing a thumb (toggle off) not tested. |
| 4 | Unobtrusive rating prompt after a few replies | Covered | conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating | Prompt absent before, shown after Nth (1) reply. |
| 5 | Asked to rate on End chat if not rated | Covered | conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating<br>version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | 'Before you go' prompt with focus on 1 of 5 at End chat. |
| 6 | Dismiss rating prompt; not reappear until end | Covered | conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating | 'Not now' hides it across reload and further replies; reappears on End chat. |
| 7 | Change Conversation Rating later | Covered | conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating | Rated 2 then 4; Studio change log shows both. |
| 8 | Feedback and rating controls accessible | Covered | message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer<br>conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating | axe on host page incl. iframe with thumbs/comment and rating prompt; focus on end prompt. |
| 9 | Conversations list per Agent/Project with filters | Partial (low) | conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace<br>message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer<br>conversation-rating › Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating<br>guardrail-analytics › a Visitor's blocked attack shows in the Version's block rate and in the Conversations filtered by Guardrail outcome | Per-Agent and per-Project lists; Version, feedback, rating, Guardrail, Visitors/Playground filters asserted; date filter not tested. |
| 10 | Read Conversation with feedback, comment, Trace inline | Covered | conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace<br>message-feedback › a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer | Messages list, 'Thumbs down · for Agent Version v1', comment, Trace folds under reply. |
| 11 | Trace shows retrieved Chunks, scores, cited, linked to viewer | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search<br>five-minute-demo › the five-minute demo | Retrieved Chunks table with 'Cited', citation chip links to Document viewer #chunk; numeric scores not explicitly asserted. |
| 12 | Deleted Document tombstone in Trace | Covered | retention › a Trace keeps a deleted Document's name as a tombstone, and an Owner deletes a Conversation on request | 'Chunk from deleted Document leave-policy.md' cell. |
| 13 | Conversations and Messages count per Version | Covered | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | Volume card '1 Conversation', '2 replies'. |
| 14 | Mean and p95 tokens per reply per Version | Partial (low) | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | Tokens card only asserts 'n = 0 replies that asked a model'; no mean/p95 values ever shown. |
| 15 | Cost per Conversation per Version with frozen prices | Gap (medium) | – | No e2e asserts a cost KPI per Version or frozen-price behaviour. Backend test_version_metrics/test_prices and AnalyticsTab.test cover. |
| 16 | Thumbs-up rate with 95% CI and n | Covered | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count<br>version-comparison › an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV<br>five-minute-demo › the five-minute demo | '50%', '95% interval 9% to 91%', 'n = 2 votes', Low sample marker. |
| 17 | Mean Conversation Rating with count | Covered | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | '2.0 of 5', 'n = 1 rating'. |
| 18 | Guardrail block rate and fallback rate per Version | Covered | guardrail-analytics › a Visitor's blocked attack shows in the Version's block rate and in the Conversations filtered by Guardrail outcome<br>version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | Block rate '33%… 1 of 3 replies blocked'; Fallback '100%… 2 of 2'. |
| 19 | p95 TTFT and total latency per Version | Partial (low) | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | p95 latency card asserts only 'n = 2 replies'; TTFT KPI not asserted. |
| 20 | Compare two Versions side by side, differences highlighted | Covered | version-comparison › an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV | Comparison table cells incl. difference and 'Better' column. |
| 21 | Config diff next to comparison metrics | Covered | version-comparison › an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV | 'Configuration changes' region shows Retrieval Mode and system prompt diff. |
| 22 | Time series with Live Version change markers | Covered | time-series › the Editor sees a Visitor's Conversation over time, markers where the Live Version changed, and a confounder note once a Document is added | Live Version changes list and reference line labelled 'v1, v2, v1'; table/month views. |
| 23 | Choose date range | Covered | version-comparison › an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV | From/To (UTC) fields change comparison to zero and back. |
| 24 | Playground excluded from analytics | Covered | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count | Playground conversation sent; Volume shows 1 Conversation (Visitor only). |
| 25 | Warning that KB changes may confound comparison | Covered | time-series › the Editor sees a Visitor's Conversation over time, markers where the Live Version changed, and a confounder note once a Document is added | Note 'Documents changed during this period… may confound the comparison' after upload. |
| 26 | Export Version comparison as CSV | Covered | version-comparison › an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV | Download filename and CSV rows asserted. |
| 27 | Set Organisation Retention Window (default 90) | Covered | retention › an Owner sets the Retention Window, and the change is audited | Default 90, set 30, persisted after reload, audited. |
| 28 | Automatic purge of text/comments past window | Not e2e | – | Needs controllable clock: backend test_retention.py. |
| 29 | Aggregate metrics kept after purge | Not e2e | – | Backend test_retention.py compares metrics before/after purge; e2e only shows 'numbers stay in the metrics' copy. |
| 30 | Delete a specific Conversation on request | Covered | retention › a Trace keeps a deleted Document's name as a tombstone, and an Owner deletes a Conversation on request | Confirm dialog, transcript replaced, Visitor token 401, list shows '(deleted on request)'. |
| 31 | Purge applies to archived Agents and Projects | Not e2e | – | Backend test_retention.py (archived Agents purged). |
| 32 | Retention changes and deletions audited | Covered | retention › an Owner sets the Retention Window, and the change is audited<br>retention › a Trace keeps a deleted Document's name as a tombstone, and an Owner deletes a Conversation on request | organisation.retention_window_changed in Audit tab; conversation.deleted via API. |
| 33 | Org-wide cost per Project and Agent incl. Playground | Covered | organisation-cost › an Owner opens the Cost page from the navigation and sees each Project's and Agent's cost, the Playground in its own column<br>five-minute-demo › the five-minute demo | Cost by Project/Agent tables with Visitors/Playground/Evaluation columns. Amounts not checked. |

<a id="spec-08"></a>
### 08 Spec 08: Guardrails and evaluation

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Agents have no tools acting outside the conversation | Not e2e | – | Architectural guarantee; backend agentic tests (test_agentic_guardrails/test_agentic_retrieval) and design. |
| 2 | Visitor input and Chunks marked as untrusted in prompt | Not e2e | – | Prompt assembly: backend/tests/unit/test_prompt_assembly.py. |
| 3 | Injection classifier on by default | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>guardrail-analytics › a Visitor's blocked attack shows in the Version's block rate and in the Conversations filtered by Guardrail outcome | Fresh Agent with no setup blocks 'Ignore all previous instructions…' in Playground and widget. |
| 4 | Choose block/warn/log per Agent | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override | Input Guardrail mode select switched to log and warn; outcomes differ. |
| 5 | Block stops before model with refusal | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>llm-classifier › an Agent's LLM classifier refuses what it flags, and its fail mode decides an outage<br>embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version | 'Blocked by the input Guardrail: the model wasn't asked', 0 tokens, refusal text. |
| 6 | Warn: pass through with caution, flagged | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Answered; Trace 'flagged and answered with a caution to the model'. |
| 7 | Log: record verdict only | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Trace 'logged only and answered as usual'. |
| 8 | Optional LLM classifier with own credential | Covered | llm-classifier › an Agent's LLM classifier refuses what it flags, and its fail mode decides an outage | LLM classifier flags jailbreak and refuses; Trace names it. |
| 9 | LLM classifier fail open/closed on provider error | Covered | llm-classifier › an Agent's LLM classifier refuses what it flags, and its fail mode decides an outage | Default closed refuses on outage; switched to open answers and Trace says unchecked. |
| 10 | Set the refusal text Visitors see | Gap (medium) | – | Only default 'Sorry, I can't help…' asserted; no test sets custom refusal text. Backend test_agent_config covers field. |
| 11 | Canary token; reply stopped if canary appears | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>attack-panel › the canary cuts off the encoded attack's leak: the secret never reaches the page<br>attack-panel › ${expected.button}: shows the reply and each Guardrail layer's outcome | Trace 'Canary token: leak, cut off and replaced'; attack panel canary row. |
| 12 | Leaked reply cut off cleanly, replaced with fallback | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>attack-panel › the canary cuts off the encoded attack's leak: the secret never reaches the page<br>five-minute-demo › the five-minute demo | Fallback shown, secret/canary fragment never on page. |
| 13 | Chunks with AI-aimed instructions flagged at upload | Covered | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it<br>five-minute-demo › the five-minute demo | Seed handbook Chunk flagged with classifier score; ordinary Chunk not. |
| 14 | Per-Project: exclude flagged Chunks or only mark | Partial (medium) | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it | Setting toggled to Exclude in UI, but effect on retrieval never asserted. Backend test_flagged_chunks covers. |
| 15 | Clear false-positive Chunk flag, audited | Partial (low) | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it | Clear flag asserted in viewer; Audit Event not asserted. Backend test_flagged_chunks audits. |
| 16 | Guardrail outcomes shown in Trace | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in<br>llm-classifier › an Agent's LLM classifier refuses what it flags, and its fail mode decides an outage | Trace Guardrails list: layer, verdict, score, action text for block/log/warn/canary/LLM. |
| 17 | Guardrail block rate per Version in analytics | Covered | guardrail-analytics › a Visitor's blocked attack shows in the Version's block rate and in the Conversations filtered by Guardrail outcome | KPI card '33%', '1 of 3 replies were blocked'. |
| 18 | Filter Conversations by Guardrail events | Covered | guardrail-analytics › a Visitor's blocked attack shows in the Version's block rate and in the Conversations filtered by Guardrail outcome | Guardrail filter Blocked/Without; URL guardrail=blocked; transcript badge. |
| 19 | Alert badge when block rate spikes | Gap (medium) | – | No e2e triggers spike badge. Backend test_guardrail_analytics and AgentsTab.test.tsx cover the flag/badge. |
| 20 | Versioned attack evaluation suite across categories | Not e2e | – | backend/evals/attack_suite.json + unit test_attack_eval_suite.py. |
| 21 | Attack cases declare expected per-layer outcome | Not e2e | – | attack_suite.schema.json; unit test_attack_eval_runner/report. |
| 22 | Suite runs in CI on every PR (mocked model) | Not e2e | – | CI gate: .github/workflows/guardrails-eval.yml mocked job. |
| 23 | Suite runs nightly vs real model with report | Not e2e | – | guardrails-eval.yml nightly real-model job. |
| 24 | Benign cases measure false positives | Not e2e | – | Eval suite content; test_attack_eval_suite.py. (Attack panel benign control is e2e-covered.) |
| 25 | Attack panel fires attacks and shows stopping layer | Covered | attack-panel › has a button per attack category and a benign control<br>attack-panel › ${expected.button}: shows the reply and each Guardrail layer's outcome<br>attack-panel › the canary cuts off the encoded attack's leak: the secret never reaches the page<br>five-minute-demo › the five-minute demo | Each button: acted layer text, Input/Canary rows, reply text; axe clean. |

<a id="spec-09"></a>
### 09 Spec 09: Terraform and deploy

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Whole AWS environment defined in Terraform | Not e2e | – | infra: infra/envs/demo + modules; infra.yml validate/terraform test |
| 2 | Reusable modules composed by environment root | Not e2e | – | infra: infra/modules/* with contract.tftest.hcl |
| 3 | Remote S3 state with native locking | Not e2e | – | infra: infra/envs/demo/backend.tf; infra/tests/backend.test.sh |
| 4 | Documented bootstrap for state bucket and OIDC role | Not e2e | – | infra/docs: infra/bootstrap (bootstrap.tftest.hcl), docs/infra-bootstrap.md |
| 5 | Private subnets with fck-nat egress | Not e2e | – | infra: modules/network contract test |
| 6 | Variable to switch to managed NAT gateway | Not e2e | – | infra: modules/network contract test |
| 7 | RDS Postgres 16 pgvector, encrypted, private, backups | Not e2e | – | infra: modules/database contract test |
| 8 | ElastiCache Redis encrypted with auth | Not e2e | – | infra: modules/cache contract test |
| 9 | Private encrypted S3 buckets, OAC for static | Not e2e | – | infra: modules/storage contract test |
| 10 | Documents bucket CORS only from CloudFront origin | Not e2e | – | infra: modules/storage contract test |
| 11 | API, worker, Beat as separate right-sized Fargate services | Not e2e | – | infra: modules/ecs contract test (task-settings.json) |
| 12 | Least-privilege IAM task role per service | Not e2e | – | infra: modules/ecs contract test; checkov |
| 13 | API role assumes customer Bedrock roles only with external ID | Not e2e | – | infra: modules/ecs contract test |
| 14 | KMS key with rotation for credential envelope encryption | Not e2e | – | infra: modules/kms contract test |
| 15 | Platform secrets in Secrets Manager injected into tasks | Not e2e | – | infra: modules/ecs contract test |
| 16 | ALB only from CloudFront prefix list with origin header | Not e2e | – | infra: modules/ecs/cdn contract tests |
| 17 | One CloudFront distribution routing static and API paths | Not e2e | – | infra: modules/cdn contract test; scripts/deploy/smoke.sh |
| 18 | CloudFront forwards headers/cookies, no buffering for SSE | Not e2e | – | infra: modules/cdn contract test; streaming not checked post-deploy |
| 19 | SPA fallback routing for Studio deep links | Not e2e | – | infra: modules/cdn contract test; smoke.sh checks Studio loads |
| 20 | Optional domain_name adds Route 53 and ACM | Not e2e | – | infra: modules/cdn contract test |
| 21 | ECR repos with scan on push and lifecycle | Not e2e | – | infra: modules/ecr contract test |
| 22 | CloudWatch log groups with retention, JSON logs | Not e2e | – | infra: modules/ecs contract test; JSON logging backend unit tests |
| 23 | Logfire token via Secrets Manager when present | Not e2e | – | infra: modules/ecs contract test |
| 24 | Images built and pushed to ECR on merge to main | Not e2e | – | CI: .github/workflows/deploy.yml push job |
| 25 | Manual workflow to apply demo at image tag | Not e2e | – | CI: deploy.yml workflow_dispatch; scripts/deploy/deploy.sh (+tests) |
| 26 | Migrations as gated one-off ECS task before rollout | Not e2e | – | CI/deploy: scripts/deploy/deploy.sh and scripts/deploy/tests |
| 27 | Manual workflow to destroy demo environment | Not e2e | – | CI: .github/workflows/destroy.yml; scripts/deploy/destroy.sh |
| 28 | terraform plan on infra PRs when OIDC configured, else skipped | Not e2e | – | CI: infra.yml plan gate; scripts/ci/plan-gate.sh (+tests) |
| 29 | CI authenticates via GitHub OIDC limited to repo branches | Not e2e | – | infra: modules/ci-oidc contract test |
| 30 | fmt, validate, tflint, checkov on every PR | Not e2e | – | CI: .github/workflows/infra.yml |
| 31 | terraform test per module asserting contracts | Not e2e | – | infra: infra/modules/*/tests/contract.tftest.hcl |
| 32 | Apply prints URL and runs smoke check | Not e2e | – | deploy: scripts/deploy/smoke.sh in deploy.yml |
| 33 | Tags on every resource | Not e2e | – | infra: default_tags; contract tests |
| 34 | Documented rough monthly cost | Not e2e | – | docs: docs/deploy-demo.md |

<a id="spec-10"></a>
### 10 Spec 10: Seed data and showcase

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | make dev && make seed gives demo in <5 min | Not e2e | – | Developer tooling/timing; e2e runs after make seed but doesn't time it. |
| 2 | Seeding is idempotent | Not e2e | – | backend test_seed.py test_seeding_twice_changes_nothing. |
| 3 | make seed-reset recreates only demo Organisation | Not e2e | – | backend test_seed.py test_reset_recreates_only_the_demo_organisation. |
| 4 | Seed runs on AWS via one-off ECS task | Not e2e | – | Infra: .github/workflows/seed.yml + scripts/deploy/seed.sh. |
| 5 | Seed works without real Provider Credential | Covered | seed › the demo model is the Default Model, labelled as a demo<br>five-minute-demo › the five-minute demo<br>demo-pages › the shop page on the allowed origin shows the Product FAQ as a bubble, and a Visitor chats with it | Demo model labelled as Default Model; canned demo answers in Playground and widget, no key. |
| 6 | Seed accepts real Provider Credential from env | Not e2e | – | backend test_seed.py test_a_real_credential_is_read_from_the_environment. |
| 7 | Sign in as demo Owner or Editor with printed creds | Covered | seed › the demo Owner finds Northwind's Project, Documents, Tags and Agents<br>seed › one seeded Agent is Agentic and one Automatic, over the same Project; the Guardrail demo Agent is Automatic | signInAs with owner@ and editor@northwind.example. |
| 8 | Realistic synthetic Documents (handbook, FAQ, returns, deck) | Covered | seed › the demo Owner finds Northwind's Project, Documents, Tags and Agents | Four Documents listed and Ready (md, docx, pptx). |
| 9 | Planted instruction flagged in viewer | Covered | five-minute-demo › the five-minute demo | Viewer shows flagged 'A note for AI assistants' Chunk. |
| 10 | HR/product Tags with each Agent scoped | Partial (low) | seed › the demo Owner finds Northwind's Project, Documents, Tags and Agents | Document Tags HR/Products asserted; seeded Agents' Tag scoping not asserted. |
| 11 | HR Agent three Versions, v2 reverted in Live History | Covered | five-minute-demo › the five-minute demo | Timeline 'Published v1 → v3', 'Reverted v2 → v1', 'Published v1 → v2'. |
| 12 | Instructions two Versions, one Agent behind | Gap (low) | – | Seeded Instructions/behind state not checked e2e. Backend test_seeded_history covers. |
| 13 | Weeks of synthetic conversations showing honest difference | Covered | five-minute-demo › the five-minute demo | Thumbs-up v2 < v1 < v3 each with 95% interval. |
| 14 | Small-sample Version shows low confidence | Covered | five-minute-demo › the five-minute demo | v3 Volume card 'Low sample'. |
| 15 | Distinctive Org Theme and per-Agent override | Gap (low) | – | Seeded Theme/override not asserted in e2e. Backend test_seed checks Theme colours/font. |
| 16 | Demo shop page with bubble and inline page | Covered | demo-pages › the shop page on the allowed origin shows the Product FAQ as a bubble, and a Visitor chats with it<br>demo-pages › the help-centre page shows the same Agent inline<br>five-minute-demo › the five-minute demo | Shop page bubble chat; help-centre inline widget. |
| 17 | Disallowed-origin page visibly fails | Covered | demo-pages › a page on a disallowed origin pastes the same snippet, and the browser refuses to show the widget<br>five-minute-demo › the five-minute demo | 'This site may not show the chat'; iframe is chrome-error page. |
| 18 | Attack panel one-click attacks with layer shown | Covered | five-minute-demo › the five-minute demo<br>attack-panel › has a button per attack category and a benign control<br>attack-panel › ${expected.button}: shows the reply and each Guardrail layer's outcome | All five buttons with expected Input/Canary outcomes. |
| 19 | Low budget Agent exhausted by button; unavailable + Studio alert | Covered | demo-pages › one click spends the Low-budget helper's Token Budget: the widget shows its unavailable text and the Studio its alert<br>five-minute-demo › the five-minute demo | Button spends budget; widget alert text; Agent list 'Budget spent'. |
| 20 | Audit Events populated from seeded history | Covered | five-minute-demo › the five-minute demo | Audit tab rows for agent.reverted, agent.bulk_published, instructions_published. |
| 21 | README explains product, diagram, stack, links docs | Not e2e | – | Docs; .github/workflows/links.yml checks relative links. |
| 22 | Five-minute demo script in README | Not e2e | – | Docs; the script itself is automated by five-minute-demo.spec.ts. |
| 23 | README sections on testing strategy and security | Not e2e | – | Docs content; links.yml only. |
| 24 | CI status and coverage badges | Not e2e | – | Docs/CI. |
| 25 | README AWS deploy/destroy instructions with cost | Not e2e | – | Docs; deploy.yml/destroy.yml workflows. |

<a id="spec-11"></a>
### 11 Spec 11: Studio design system and reskin

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Studio looks calm and consistent page to page | Not e2e | – | Visual design; reviewed via light/dark evidence screenshots; palette ratchet + axe sweep guard regressions. |
| 2 | Choose light or dark Appearance | Gap (low) | – | No e2e clicks an Appearance control; only emulateMedia. Unit: apps/studio/src/design/appearance.test.tsx. |
| 3 | Follow system colour scheme until chosen | Partial (low) | accessibility › every signed-in page has no WCAG 2.2 AA violations, in the light and the dark Appearance | Emulates dark colour scheme and runs axe, but never asserts the dark Appearance is applied. Unit-tested in appearance.test.tsx. |
| 4 | Appearance remembered in this browser | Gap (low) | – | No e2e reload-persistence check. Unit: appearance.test.tsx. |
| 5 | No flash of other Appearance on load | Gap (low) | – | Not asserted e2e; likely main.test.tsx / inline boot script unit test. |
| 6 | Breadcrumb shows where I am | Covered | sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row | Crumbs asserted exactly (Project / Agents / Agent); spec 12 dropped Organisation crumb. |
| 7 | Switch Organisation/Project/section/Agent from its crumb | Partial (medium) | organisation-switcher › a Member of two Organisations switches between them, and the choice survives reloads and sign-ins<br>sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Superseded by sidebar switchers (spec 12). Org switch covered; switching to another Project or Agent (▾) not e2e. |
| 8 | Current page marked in breadcrumb | Covered | sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row | breadcrumb() helper asserts the current crumb. |
| 9 | Section switchers are real links | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Sections are link roles in sidebar lists; new-tab opening not exercised. |
| 10 | Number hints 1–6 in switcher menus | Not e2e | – | Superseded: spec 12 #71 removes number hints; sidebar.spec asserts exact link names (no numbers). |
| 11 | Members and Audit hidden from Editors | Covered | members › an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends | Editor's settings tab row lacks Members and Audit; API 403 also asserted. |
| 12 | Pages start with their own title and content | Covered | sidebar › the main content keeps its 1160 px column beside a sidebar of about 240 px | h1 asserted on every page; navigation moved to sidebar; layout geometry checked. |
| 13 | Archive/Delete in ⋯ menu | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>project-deletion › an Owner deletes an archived Project after typing its name, and its stored files go too | More Project actions menu drives Archive and Delete permanently. |
| 14 | One clearly primary button per view | Not e2e | – | Visual hierarchy (button variant); enforced by design components and review, not assertable by role. |
| 15 | Destructive confirmations name the thing and consequence | Covered | project-deletion › an Owner deletes an archived Project after typing its name, and its stored files go too<br>retention › a Trace keeps a deleted Document's name as a tombstone, and an Owner deletes a Conversation on request | Alertdialogs named after the item, type-to-confirm, consequence text asserted. |
| 16 | Short confirmation after change, with Undo | Partial (low) | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Success notices asserted in many specs; no e2e exercises Undo anywhere. |
| 17 | Project key figures as cards atop Documents | Partial (low) | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it | Knowledge Base region 'Flagged chunks' asserted; Documents/Chunks/Embedding Model cards not all checked. |
| 18 | Document table with status, Tag pills, flagged count, ⋯ | Covered | documents › an Owner uploads the seed handbook and it goes from Queued to Ready<br>tags › an Editor organises Documents with Tags and filters the list by name, status and Tag | Columns, status cell, flagged count and row ⋯ actions exercised; dot styling not. |
| 19 | Playground main column, config in collapsible sections | Covered | agent-config › an Owner configures every group, the Draft autosaves and the Playground uses the Model override | Configuration complementary with <details> groups opened via openSettings helper. |
| 20 | Trace folded under each Playground answer | Covered | playground › an Owner creates an Agent, asks its Draft a question and the answer streams in | Clicks 'Trace' under answer and reads its group. |
| 21 | Versions timeline, pick two to compare | Covered | version-comparison › an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV |  |
| 22 | Diffs mark lines with + and − | Covered | agent-drafts › an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a conflict | Rows read '2−Removed…', '2+Added…'. |
| 23 | Embed snippet copy and launcher choice | Partial (low) | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version | Copy to clipboard covered; launcher choice in the Studio not driven (only via URL param). |
| 24 | Allowed Origins editable list warns when empty | Partial (medium) | operational-settings › an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget | Add/remove/validate covered; empty-list warning never asserted. |
| 25 | Token Budget meter turns warning/danger colour | Partial (low) | token-budget › an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and | Meter value and spent alert asserted; colour states not (colour is not e2e-asserted by policy). |
| 26 | Conversations list beside transcript with filters | Covered | conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace | Visitors and Version filters, list beside transcript; date filters not exercised. |
| 27 | Guardrail blocks and flagged citations marked in transcripts | Covered | guardrail-analytics › a Visitor's blocked attack shows in the Version's block rate and in the Conversations filtered by Guardrail outcome<br>conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace | 'Blocked by guardrail' badge asserted; flagged-citation badge less explicit. |
| 28 | KPIs show 95% intervals, sample sizes, small-sample mark | Covered | version-kpis › a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count |  |
| 29 | Time series marks Live changes and Document changes | Covered | time-series › the Editor sees a Visitor's Conversation over time, markers where the Live Version changed, and a confounder note once a Document is added |  |
| 30 | Every chart has table view and hover readout | Partial (low) | time-series › the Editor sees a Visitor's Conversation over time, markers where the Live Version changed, and a confounder note once a Document is added | Table view covered for time series only; hover readout and other charts not. |
| 31 | Empty, loading, error states explain next step | Partial (low) | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>playground-errors › a provider failure is explained, and a reset starts a new Conversation | Some empty/error states asserted; loading states not (network-seam unit tests per spec). |
| 32 | Switchers, menus, dialogs keyboard-operable and announced | Partial (medium) | sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link | Drawer keyboard path covered; menus/dialogs keyboard paths only in Testing Library unit tests. |
| 33 | WCAG AA contrast in both Appearances | Covered | accessibility › every signed-in page has no WCAG 2.2 AA violations, in the light and the dark Appearance | Also design/tokens.test.ts token contrast contract. |
| 34 | Top bar and breadcrumb wrap/collapse on narrow screens | Covered | sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row | No horizontal scroll at 390px, banner height asserted. |
| 35 | Widget and preview keep Organisation Theme | Covered | branded-widget › the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark<br>theme › an Owner changes the primary colour, sees the preview update and the contrast warning, and saves | Isolation from Studio tokens implied, not asserted directly. |
| 36 | Shared components and class recipes | Not e2e | – | Code structure; design/*.test.tsx unit tests. |
| 37 | CI blocks Tailwind palette classes | Not e2e | – | frontend/scripts/palette-ratchet (ratchet.test.mjs) run in .github/workflows/frontend.yml. |
| 38 | Light/dark screenshots per slice | Not e2e | – | Process: docs/tickets/*-evidence screenshots; no automated pixel diffs. |

<a id="spec-12"></a>
### 12 Spec 12: Reskin fixes and sidebar navigation

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| | **Projects list** | | | |
| 1 | Projects list looks like rest of Studio | Not e2e | – | Visual; axe sweep covers projects page; palette ratchet. |
| 2 | Projects page title and one-line description | Partial (low) | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | h1 'Projects' asserted; description line not. |
| 3 | Table card with name, description, Document and Agent counts | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Row cells asserted exactly. |
| 4 | Project name is an un-underlined link like Agents list | Partial (low) | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Link role covered; styling not e2e-assertable. |
| 5 | Long descriptions kept to one line | Gap (low) | – | Truncation not checked in any test; CSS-only. |
| 6 | Count columns right-aligned mono | Not e2e | – | Styling; spec says tests don't assert classes. |
| 7 | Active / Archived filter above table | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | radiogroup 'Projects shown' toggled. |
| 8 | Archived Projects listed with archive date | Gap (low) | – | Archived list rows' date never asserted. |
| 9 | Owner restores archived Project from its row | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>projects › an Editor creates and archives a Project but only an Owner restores it |  |
| 10 | Editor told only Owners can restore | Partial (low) | projects › an Editor creates and archives a Project but only an Owner restores it | Message asserted on Project page after archiving, not in the archived list view. |
| 11 | Designed empty state for no (archived) Projects | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>project-deletion › an Owner deletes an archived Project after typing its name, and its stored files go too | 'No Projects yet' and 'No archived Projects' headings. |
| 12 | Loading placeholder while Projects load | Gap (low) | – | Network-seam unit tests per spec. |
| 13 | Clear error state when Projects fail to load | Gap (low) | – | Network-seam unit tests per spec. |
| 14 | Success notice after delete or restore | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited<br>project-deletion › an Owner deletes an archived Project after typing its name, and its stored files go too | 'was restored' and 'is being deleted permanently' asserted. |
| | **New Project and Edit details** | | | |
| 15 | New Project button top right | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Button exists and opens form; position not asserted. |
| 16 | New Project opens dialog with Name and Description | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Form 'New Project' with both fields. |
| 17 | Dialog fields styled like other forms | Not e2e | – | Styling. |
| 18 | New Project opens on create | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | h1 shows the new Project after Create. |
| 19 | Create errors shown inside dialog, input kept | Gap (medium) | – | No e2e for create failure (e.g. duplicate/blank); unit seam. |
| 20 | Cancel/Escape close dialog, nothing created, focus back | Gap (low) | – | Not in e2e; Dialog unit tests cover keyboard path. |
| 21 | New Project hidden in Archived view | Gap (low) | – | Not asserted. |
| 22 | Edit details opens a dialog | Covered | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Form 'Project details' opened from Edit details. |
| 23 | Edit dialog shows current name and description | Gap (low) | – | Test overwrites fields without checking prefilled values. |
| 24 | Toast after saving details, header shows new name | Partial (low) | projects › an Owner creates, renames, archives and restores a Project, and each step is audited | Header new name asserted; toast not. |
| 25 | Edit details button stays in place | Gap (low) | – | Layout stability not asserted. |
| | **Organisation cost** | | | |
| 26 | Cost page looks like other data pages | Not e2e | – | Visual; axe sweep covers cost page. |
| 27 | Segmented control by Project / by Agent | Covered | organisation-cost › an Owner opens the Cost page from the navigation and sees each Project's and Agent's cost, the Playground in its own column | radiogroup 'Break down by' switches tables. |
| 28 | From and To date filters | Gap (medium) | – | Date filters never driven e2e; unit seam per spec. |
| 29 | Period shown under filters | Gap (low) | – | Not asserted. |
| 30 | Amounts right-aligned mono, total row set apart | Partial (low) | organisation-cost › an Owner opens the Cost page from the navigation and sees each Project's and Agent's cost, the Playground in its own column | 'All Projects' total row asserted; alignment/styling not. |
| 31 | Total, Visitor, Playground summary cards | Covered | organisation-cost › an Owner opens the Cost page from the navigation and sees each Project's and Agent's cost, the Playground in its own column | List 'Spend for the period' items asserted. |
| 32 | Empty state when nothing spent | Gap (low) | – | Not asserted. |
| 33 | Error notice for bad dates (From>To, >366 days) | Gap (medium) | – | 422 message covered only at network seam. |
| 34 | Editor told only Owners see spend | Gap (medium) | – | Editor never visits Cost e2e; permission messaging unverified end to end. |
| 35 | Cost table scrolls sideways inside card on phone | Gap (low) | – | No 390px check on Cost page. |
| | **Invite someone** | | | |
| 36 | Invite someone button top right of Members | Covered | invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account<br>invites › an existing Member accepts a copied link, and a revoked link stops working |  |
| 37 | Invite dialog with Email, Role, Email-the-link | Covered | invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account<br>invites › an existing Member accepts a copied link, and a revoked link stops working | All three controls used. |
| 38 | Dialog closes and toast confirms invite | Partial (low) | invites › an Owner invites an Editor, who opens the email in Mailpit and joins with a new account<br>invites › an existing Member accepts a copied link, and a revoked link stops working | 'New invite' region text and reopening implied close; toast and dialog close not asserted explicitly. |
| 39 | New invite link and expiry shown after close | Partial (low) | invites › an existing Member accepts a copied link, and a revoked link stops working | Link value read and used; expiry not asserted. |
| 40 | Invalid email / existing Member reported in dialog | Gap (medium) | – | No e2e for invite validation errors. |
| 41 | New link from pending invite shows same panel | Gap (low) | – | Not exercised. |
| 42 | Member row role select styled like other selects | Covered | select-chevron › selects draw the design system's chevron, inset like their text, in both Appearances | Table-cell 'Role for …' select checked. |
| | **Selects** | | | |
| 43 | Chevron inset matches text inset | Covered | select-chevron › selects draw the design system's chevron, inset like their text, in both Appearances | backgroundPositionX = calc(100% - paddingLeft). |
| 44 | Long option text never under chevron | Covered | select-chevron › selects draw the design system's chevron, inset like their text, in both Appearances | paddingRight ≥ 36px asserted. |
| 45 | Chevron visible in dark Appearance | Partial (low) | select-chevron › selects draw the design system's chevron, inset like their text, in both Appearances | Asserts chevron SVG changes in dark; contrast/visibility not measured. |
| 46 | Disabled select chevron dimmed | Gap (low) | – | No disabled select checked. |
| | **Project Settings** | | | |
| 47 | Project Settings look like Organisation settings | Not e2e | – | Visual; axe sweep covers project-settings. |
| 48 | Settings heading and short description | Gap (low) | – | Not asserted. |
| 49 | Each setting in its own titled card | Covered | embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over<br>ocr › an Owner turns OCR on for a Project and reprocesses a Document with it through retry<br>documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it | Region 'Embedding Model', OCR checkbox, radiogroup 'Flagged Chunks'. |
| 50 | Current Embedding Model shown with Change button | Covered | embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over |  |
| 51 | Change dialog warns about re-embedding | Covered | embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over | Dialog text asserted. |
| 52 | Re-embed progress meter with Chunk counts | Partial (low) | embedding-models › changing the model of a Project with Documents re-embeds it in the background and switches over | Completion asserted via UI and API; in-progress meter never asserted. |
| 53 | Failed re-embed shown as error with reason | Gap (medium) | – | No failure path e2e. |
| 54 | OCR labelled toggle with hint and state | Covered | ocr › an Owner turns OCR on for a Project and reprocesses a Document with it through retry |  |
| 55 | Flagged Chunk mode two described choices | Covered | documents › the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it |  |
| 56 | Setting shows choice at once, disabled while saving | Gap (low) | – | Optimistic/disabled covered only at network seam. |
| 57 | Archived Project settings shown disabled, no model change | Gap (medium) | – | No e2e; API refuses changes (409) per projects.spec for rename only. |
| | **Sidebar navigation** | | | |
| 58 | Every destination is a sidebar link | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are |  |
| 59 | Current page link highlighted | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are<br>sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link | aria-current checked via currentSection. |
| 60 | Organisation switcher for multi-org Members | Covered | organisation-switcher › a Member of two Organisations switches between them, and the choice survives reloads and sign-ins<br>invites › an existing Member accepts a copied link, and a revoked link stops working |  |
| 61 | Single Organisation shown as plain text | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Name visible; absence of switcher button not explicitly asserted. |
| 62 | Owner sees Projects, Cost, Settings links | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are |  |
| 63 | Editor's sidebar omits Cost | Gap (medium) | – | No e2e inspects an Editor's 'Organisation sections'; shell unit tests only. |
| 64 | Project name with switcher in sidebar | Partial (low) | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Switcher to All Projects covered; jumping to another Project not. |
| 65 | Project section links under Project | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Exact six section names asserted. |
| 66 | Section stays highlighted on Agent/Document/Conversation | Partial (low) | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Only Agent → Agents asserted; Document and Conversation not. |
| 67 | Plain breadcrumb of links | Covered | sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row | No buttons in breadcrumb; crumb click goes up. |
| 68 | Profile, Security, Sign out only in account menu | Covered | sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row |  |
| 69 | MFA-required Member's sidebar offers only Security | Covered | require-mfa › an Owner requires MFA, and an Editor is forced to enrol on their next visit |  |
| 70 | Page actions stay in top bar | Covered | agent-publish › an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log | publishAgent helper clicks Publish in the banner; used across many specs. |
| 71 | No unexplained numbers beside links | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are | Exact link names asserted (no number hints). |
| | **Agent pages** | | | |
| 72 | Agent views as tabs under Agent's name | Covered | embed › an Editor copies a live Agent's Embed Snippet, allows the host page's origin, and a Visitor there chats with the Live Version<br>conversations › an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace | openAgentView uses the 'Agent views' tab row in many specs. |
| 73 | Switch Agent from ▾ on its name | Gap (medium) | – | Only harness/agent-navigation.spec.ts (fake page); no real-stack test. |
| 74 | One page heading: the Agent's name | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are<br>sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row | h1 is the Agent's name. |
| 75 | Conversations tab stays selected on Agent's Conversation | Gap (low) | – | Not asserted. |
| | **Narrow screens and accessibility** | | | |
| 76 | Sidebar opens as drawer from menu button on phone | Covered | sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link |  |
| 77 | Drawer closes on link, Escape, outside press | Covered | sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link |  |
| 78 | Focus trapped in drawer and returned to button | Covered | sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link |  |
| 79 | Current link focused when drawer opens | Covered | sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link |  |
| 80 | Breadcrumb shows last two crumbs on phone | Covered | sidebar › the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row |  |
| 81 | Sidebar named nav landmark with aria-current | Covered | sidebar › an Owner moves around the Organisation and a Project from the sidebar, which marks where they are<br>sidebar › on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link | navigation 'Studio' and aria-current='page' asserted. |
| 82 | Agent views announced as tabs, selected marked | Partial (low) | – | Implemented/tested as nav 'Agent views' links with aria-current; no e2e asserts selected state on real stack. |
| 83 | New dialogs and drawer pass axe in both Appearances | Partial (medium) | accessibility › every signed-in page has no WCAG 2.2 AA violations, in the light and the dark Appearance | Drawer swept in both Appearances; New Project, Edit details and Invite dialogs not axe-scanned while open. |

<a id="spec-13"></a>
### 13 Spec 13: Agentic retrieval

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| 1 | Choose Retrieval Mode (Automatic/Agentic) in Draft | Covered | agent-config › (Agent editor test; Retrieval section) | Toggles radios, autosaves, reload shows saved mode. |
| 2 | New Agents start Agentic | Covered | agent-config › (Agent editor test; Retrieval section)<br>playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search | Asserts Agentic checked on a newly created Agent. |
| 3 | Mode control explains cost/accuracy trade-off | Covered | agent-config › (Agent editor test; Retrieval section) | Asserts radiogroup accessible description /cheaper and predictable/. |
| 4 | Retrieval Mode saved by Autosave | Covered | agent-config › (Agent editor test; Retrieval section) | nextSave after each toggle, 'All changes saved', reload confirms. |
| 5 | Retrieval Mode part of each published Version | Covered | version-comparison › (v1 Automatic vs v2 Agentic comparison) | Publishes v1 Automatic, v2 Agentic (via API); comparison shows mode change. |
| 6 | Revert restores earlier Version's Retrieval Mode | Gap (low) | – | agent-revert e2e never checks retrieval mode; backend test_agent_revert.py touches retrieval. |
| 7 | Search limit 1–5, default 3 | Covered | agent-config › (Agent editor test; Retrieval section) | Default 3, 6 rejected with message and aria-invalid, 2 saved and reloaded. |
| 8 | Search limit hidden when Automatic | Covered | agent-config › (Agent editor test; Retrieval section) | Asserts Search limit count 0 under Automatic, returns under Agentic. |
| 9 | Top-k/hybrid/min score/tags/reranker apply to every Search | Not e2e | – | Backend retrieval behaviour; test_agentic_retrieval.py. tag-scoping/reranker e2e switch to Automatic. |
| 10 | Agentic Draft save refused when model lacks tools | Partial (medium) | playground › an Agentic Agent whose Default Model can't use tools answers as Automatic, and the Trace says so | Refusal (422, reason) asserted via API PUT only; UI showing server refusal not driven in e2e (MSW DraftEditor tests). |
| 11 | Model picker shows which models support Agentic | Covered | models › (Default Model picker)<br>playground › an Agentic Agent whose Default Model can't use tools answers as Automatic, and the Trace says so | Optgroups 'Supports tools…' and 'No tools: Automatic only' asserted. |
| 12 | Default Model without tools: Agent falls back to Automatic, Trace says so | Covered | playground › an Agentic Agent whose Default Model can't use tools answers as Automatic, and the Trace says so | Answers, no Searches list, Trace warning asserted. |
| 13 | Agentic Agent answers greetings without searching | Not e2e | – | Model behaviour; fake model always searches. Backend scripted FunctionModel tests; live test_agentic_reply_live.py. |
| 14 | Agentic Agent searches before answering KB questions | Not e2e | – | Model-quality; preamble contract test + live test (live.yml does not run it; only make live). |
| 15 | Multiple searches for multi-part questions | Not e2e | – | Model behaviour; backend test_agentic_retrieval.py with scripted model. |
| 16 | Follow-up rewritten into complete search query | Not e2e | – | Model behaviour; prompt contract only. |
| 17 | Re-search with different wording when nothing useful | Not e2e | – | Model behaviour; prompt contract only. |
| 18 | Fallback Text when nothing relevant, in Agentic mode | Gap (medium) | – | No e2e Agentic reply with empty KB/fallback; backend API tests cover it. |
| 19 | Fallback decided before any answer shown | Not e2e | – | Stream ordering; backend test_agentic_streaming.py asserts no tokens before fallback. |
| 20 | Model told to answer once Search limit reached | Not e2e | – | Backend: call after limit refused, reply still answers (test_agentic_retrieval.py). |
| 21 | Trace says when reply hit Search limit | Gap (low) | – | No e2e reaches the limit (fake model searches once); MSW Trace drawer tests cover the warning. |
| 22 | Each Search shown live in Playground with query | Covered | playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search<br>five-minute-demo › step 3 Automatic then Agentic | 'Searching: <question>' list item asserted during stream. |
| 23 | Visitor sees 'Searching the knowledge base…' status | Covered | widget-accessibility › (keyboard + screen reader widget test) | Status text shown in reply, then replaced by answer. |
| 24 | Searching status announced politely once per reply | Covered | widget-accessibility › (keyboard + screen reader widget test) | Announcements status region has exactly that text; politeness level not checked. |
| 25 | Editor overrides widget searching status text | Gap (low) | – | No e2e sets searching_status; DraftEditor.test.tsx and widget unit tests cover it. |
| 26 | Trace lists each Search: query, chunks, given/excluded, duration | Partial (low) | playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search<br>five-minute-demo › step 3 Automatic then Agentic | Search heading, chunk C1 'Cited' asserted; excluded reasons and duration not asserted. |
| 27 | Citations work same in both modes, link to Document viewer | Covered | playground › a new Agent is Agentic: it searches the Knowledge Base, cites what it found and the Trace lists the Search | Agentic Sources link 'C1 northwind-staff-handbook.md' asserted; viewer not opened. |
| 28 | Chunk found twice shown once under one label | Not e2e | – | Backend: turn-wide labels test in test_agentic_retrieval.py. |
| 29 | Reply tokens/Cost include every model call | Not e2e | – | Backend summed tokens/Cost tests; e2e never checks Agentic reply cost. |
| 30 | Token Budget counts every Agentic token | Partial (low) | token-budget › (Agentic widget budget test) | Agentic reply exhausts a 1-token budget; summed count not asserted (backend covers). |
| 31 | Playground Agentic excluded from metrics/budget, in Org cost | Partial (low) | token-budget › (Agentic widget budget test) | Playground answers after budget spent; metrics exclusion and Org cost inclusion not asserted for Agentic. |
| 32 | Searches per reply in Version KPIs and comparison | Covered | version-comparison › (v1 Automatic vs v2 Agentic comparison)<br>version-kpis › (Version KPI cards) | Comparison row 0.00→1.00 and CSV; KPI card (Automatic only). |
| 33 | Retrieval Mode in Version list and Version Diffs | Partial (low) | version-comparison › (v1 Automatic vs v2 Agentic comparison)<br>version-kpis › (Version KPI cards) | Diff 'Retrieval Mode: Automatic → Agentic' and KPI card asserted; Version list column not asserted. |
| 34 | Fallback rate keeps meaning in both modes | Not e2e | – | Metric definition; backend test_search_metrics.py. |
| 35 | Knowledge Search the only, read-only tool | Not e2e | – | Security/backend; test_agentic_guardrails.py. |
| 36 | Search limited to own Project/Embedding Model/Tags | Not e2e | – | Security; backend Tag scoping/Project isolation for model-written queries. |
| 37 | Search queries checked for Canary token | Not e2e | – | Security; backend canary-in-query test. attack-panel canary e2e is Automatic. |
| 38 | Agentic chunks spotlighted/Flagged Chunk mode as Automatic | Not e2e | – | Security; backend test_agentic_guardrails.py. |
| 39 | Attack suite run in both modes in CI with pass rate each | Not e2e | – | CI: .github/workflows/guardrails-eval.yml runs both modes. |
| 40 | Remembered turns replay only text, not searches/chunks | Not e2e | – | Backend history assembly. |
| 41 | Demo Org: one Agent per mode, Trace shows difference | Covered | seed › one seeded Agent is Agentic and one Automatic, over the same Project; the Guardrail demo Agent is Automatic<br>five-minute-demo › step 3 Automatic then Agentic | Seed asserts modes; demo step 3 shows table vs per-Search Trace. |
| 42 | Demo model works Agentic without a key | Covered | five-minute-demo › step 3 Automatic then Agentic | Product FAQ (Agentic) on demo model searches and answers with citation. |
| 43 | Attack panel Guardrail demo Agent stays Automatic | Covered | seed › one seeded Agent is Agentic and one Automatic, over the same Project; the Guardrail demo Agent is Automatic | Seed test asserts Guardrail demo is Automatic. |
| 44 | Clear error event when provider fails after a Search | Gap (low) | – | playground-errors e2e has no Agentic mid-reply failure; backend typed error event test. |
| 45 | Mode/limit changes in Draft Diffs and Audit Events | Covered | agent-config › (Agent editor test; Retrieval section)<br>agent-drafts › (Draft Diff test) | Audit events retrieval_mode_changed asserted (API); Draft Diff shows 'Automatic → Agentic', '3 → 4'. |

<a id="spec-14"></a>
### 14 Spec 14: Evaluation loop

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| | **Evaluation Set and cases** | | | |
| 1 | Each Agent has its own Evaluation Set | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog<br>five-minute-demo › step 5 Evaluation view | HR helper Evaluation view lists its set. |
| 2 | Write an Evaluation Case by hand | Gap (medium) | – | No e2e creates a case from the Evaluation view; AgentEvaluation.test.tsx (MSW). |
| 3 | Every case needs at least one expectation | Gap (low) | – | Validation only in MSW/backend tests. |
| 4 | Set Expected source by choosing a Document passage | Gap (medium) | – | Source picker not driven in e2e; MSW + backend. |
| 5 | Write a Reference answer | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Reference answer filled, saved, judged in the Run. |
| 6 | Mark case Expect Fallback Text | Partial (low) | five-minute-demo › step 5 Evaluation view | Only seeded case's 'Expects the Fallback Text.' displayed; setting it not driven. |
| 7 | Case holds several Expected sources | Gap (low) | – | Backend/MSW only. |
| 8 | Edit and delete cases | Gap (medium) | – | Delete only via API cleanup; no UI edit/delete. |
| 9 | Set capped at 200 with clear message | Not e2e | – | Backend concurrent-cap test; meter shown in demo e2e. |
| 10 | Copy cases from another Agent in Project | Gap (medium) | – | Backend + MSW only. |
| 11 | Copied cases are independent | Not e2e | – | Backend data semantics (test_evaluation_set.py). |
| 12 | Cases flagged with Stale expectation | Gap (medium) | – | No e2e makes a case stale or sees the flag. |
| 13 | Latest result per case shown in set | Gap (low) | – | Not asserted in e2e; MSW. |
| 14 | Search/filter set by kind, flag, result | Gap (low) | – | MSW only. |
| | **Adding cases from real traffic** | | | |
| 15 | Add to Evaluation Set from Conversations viewer | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Thumbs-down Message → menu → dialog → saved, source from_message. |
| 16 | Same action on Playground answers | Gap (medium) | – | No e2e from Playground; MSW only. |
| 17 | Question copied in and editable | Partial (low) | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Asserts Question prefilled non-empty; never edited. |
| 18 | Cited passages offered as sources, unticked | Gap (medium) | – | Not asserted in e2e; MSW. |
| 19 | Told case keeps no link to Conversation | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | 'No link to the Conversation is kept' asserted. |
| 20 | Add-from-Message recorded as Audit Event | Gap (medium) | – | e2e checks source only, not audit; backend covers. |
| 21 | Deleting a case recorded as Audit Event | Gap (low) | – | Backend only. |
| 22 | Cases kept after Purge | Not e2e | – | Time-based Purge; task-seam test. |
| 23 | Conversation still purged/deletable | Not e2e | – | Task seam; retention.spec.ts covers purge generally, not with a case. |
| | **Running an evaluation** | | | |
| 24 | Evaluate action in Evaluation view and Publish dialog | Partial (medium) | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Publish dialog Evaluate driven; Evaluation view's Evaluate not. |
| 25 | Run compares Live vs Draft by default | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Default Evaluate in Publish dialog yields Regression vs Live v3. |
| 26 | Choose any two sides (Draft or Version) | Gap (medium) | – | Side pickers not driven; seeded v1-vs-v2 run only viewed. |
| 27 | Draft side Instructions choice | Gap (low) | – | MSW Evaluate dialog only. |
| 28 | Version side uses its pinned Instructions | Not e2e | – | Backend test_evaluation_sides.py. |
| 29 | Both sides answered at same moment, same KB | Not e2e | – | Backend. |
| 30 | Answers via real Guardrails and own Retrieval Mode | Not e2e | – | Backend test_evaluation_sides.py. |
| 31 | Estimated Cost shown before starting | Gap (medium) | – | Estimate not asserted in e2e; MSW + backend. |
| 32 | Run progress visible while running | Gap (low) | – | e2e waits for result only; MSW polling tests. |
| 33 | Cancel a running Run | Gap (medium) | – | Backend task + MSW only. |
| 34 | Evaluate disabled while Run in progress | Gap (low) | – | Backend 409 + MSW. |
| 35 | Never-published Agent Run with Draft alone | Gap (low) | – | Backend only. |
| 36 | Draft-side Run marked stale after newer revision | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Publish dialog shows 'changed since' for seeded Run. |
| 37 | Version without credential refused as side | Not e2e | – | Backend refusal test; needs credential deletion setup. |
| | **Results** | | | |
| 38 | Each side's Evaluation score | Gap (medium) | – | No e2e asserts scores. |
| 39 | Regressions listed first | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog<br>five-minute-demo › step 5 Evaluation view | Regressions list in Publish dialog; first case in Run detail is Regression. |
| 40 | Improvements shown | Gap (low) | – | Not asserted in e2e. |
| 41 | Per-expectation Verdicts with judge reason | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog<br>five-minute-demo › step 5 Evaluation view | Reason text 'lacks …' and 'Fake judge: …' asserted. |
| 42 | Grounding Verdict on every answered case | Covered | five-minute-demo › step 5 Evaluation view | Grounding fail reason 'cites nothing to support it' shown. |
| 43 | Each answer with its Trace | Gap (medium) | – | Run detail Trace drawer not opened in e2e. |
| 44 | Repeat count and Unsteady marked | Gap (low) | – | MSW only. |
| 45 | Errored case marked Error, excluded from score | Not e2e | – | Needs provider failure; backend + MSW. |
| 46 | Guardrail block on harmless case judged fail | Not e2e | – | Backend verdict test. |
| 47 | Stale expectations shown as skipped | Gap (low) | – | Not in e2e. |
| 48 | Finished Runs kept as history with details | Partial (low) | five-minute-demo › step 5 Evaluation view | Runs list with sides asserted; Instructions, Evaluation Model, repeats, Cost not. |
| 49 | Run Cost split answers vs judging | Gap (medium) | – | Backend cost + MSW only. |
| | **Publishing** | | | |
| 50 | Publish dialog warns on Regressions/lower score with reasons | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Regressions list with reason and 'You can still Publish.'; lower-score wording not checked. |
| 51 | Publish anyway after warning | Partial (medium) | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Publish button enabled, never clicked. |
| 52 | Notice for no Run / stale / Live changed | Partial (low) | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Only stale ('changed since') state seen. |
| 53 | Notice when Instructions differ from Run's | Gap (low) | – | MSW + backend only. |
| 54 | Hint when no Evaluation Set | Gap (low) | – | MSW only. |
| 55 | Rollout dialog offers Rollout evaluation | Gap (medium) | – | bulk-rollout e2e has no evaluation; RolloutEvaluation.test.tsx. |
| 56 | Rollout lists Regressions, marks 'not evaluated' | Gap (medium) | – | MSW + backend test_evaluation_rollout.py. |
| 57 | Rollout evaluation never blocks rollout | Gap (low) | – | MSW + backend. |
| | **Keeping cases valid** | | | |
| 58 | Warning before deleting Document with Expected source | Gap (medium) | – | documents e2e has no warning; MSW only. |
| 59 | Same warning before new Edition upload | Gap (medium) | – | document-editions e2e has no warning. |
| 60 | Expected sources re-checked when Edition Ready | Not e2e | – | Task seam ingestion test. |
| 61 | Surviving passages keep working after Edition | Not e2e | – | Task seam. |
| | **Organisation settings and cost** | | | |
| 62 | Owner chooses Evaluation Model in settings | Gap (medium) | – | models e2e doesn't touch it; backend + ModelsPage.test.tsx. |
| 63 | Default Model used when no Evaluation Model | Not e2e | – | Backend test_evaluation_settings.py. |
| 64 | Evaluation Model change audited | Gap (low) | – | Backend only. |
| 65 | Evaluation Model credential protected from deletion | Gap (low) | – | Backend 409 test only. |
| 66 | Owner sets repeats 1/3/5/7/9 | Gap (medium) | – | Backend + MSW only. |
| 67 | Repeats change audited | Gap (low) | – | Backend only. |
| 68 | Evaluation column in Organisation cost | Partial (low) | organisation-cost › (Cost page) | Column header present; no Evaluation amount asserted. |
| 69 | Runs excluded from Version KPIs and Token Budget | Not e2e | – | Backend test_evaluation_sides.py. |
| | **Permissions and lifecycle** | | | |
| 70 | Editor manages sets and starts Runs | Covered | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | Editor adds case and runs Evaluate. |
| 71 | Editors cannot change Evaluation Model/repeats | Gap (high) | – | Permission; backend test_editors_cannot_change_the_evaluation_model_or_repeats + MSW, no e2e. |
| 72 | Archived Agent keeps set/Runs, no new Run | Gap (medium) | – | agent-archive e2e ignores evaluation; backend covers. |
| 73 | Permanent deletion removes set and Runs | Not e2e | – | Backend test_permanent_deletion_removes_the_set_and_runs. |
| 74 | No cross-Organisation access to sets/Runs | Not e2e | – | Security isolation; backend test_evaluation_publish.py / tenant isolation. |
| | **Demo and accessibility** | | | |
| 75 | Demo HR helper set from thumbs-down + v2-vs-v1 Run with Regressions | Covered | five-minute-demo › step 5 Evaluation view<br>evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog | 12 seeded cases, v1-vs-v2 Run with Regression and reason; thumbs-down origin not asserted. |
| 76 | Evaluation UI fully accessible | Partial (medium) | evaluation-loop › an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog<br>five-minute-demo › step 5 Evaluation view | axe on Evaluation view, Run detail, Publish dialog; case editor dialog not axe-checked, no keyboard flow. |

<a id="spec-15"></a>
### 15 Spec 15: Live evaluation

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| | **Sampling** | | | |
| 1 | Set Agent Live sample rate 0-100% in Operational Settings | Gap (high) | – | Not built yet. Planned in 15-07 (set HR helper rate to 100%). |
| 2 | Sample rate applies immediately without Publishing | Gap (medium) | – | Not built yet. Implicitly exercised by 15-07 (rate then widget message, no Publish); no explicit assertion. |
| 3 | Sample rate changes recorded as Audit Events | Gap (low) | – | Not built yet. Planned at API seam only; audit.spec.ts pattern could check Audit tab. |
| 4 | Sample rate defaults to 0% | Not e2e | – | Not built yet. API/MSW default check. |
| 5 | Rate field disabled with explanation when no Evaluation budget | Gap (medium) | – | Not built yet. Planned MSW only, not e2e. |
| 6 | Replies sampled at random | Not e2e | – | Not built yet. API seam with seeded draw. |
| 7 | Guardrail-blocked replies excluded from sample | Not e2e | – | Not built yet. API seam. |
| 8 | Fallback Text replies excluded from sample | Not e2e | – | Not built yet. API seam. |
| 9 | Playground replies never sampled | Not e2e | – | Not built yet. API seam. |
| 10 | Visitor reply never waits for judging | Not e2e | – | Not built yet. Task seam (judging runs after reply); latency not e2e. |
| | **Live Verdicts** | | | |
| 11 | Judge checks every claim supported by Citations | Not e2e | – | Not built yet. API seam with scripted FunctionModel; nightly live suite (15-07). |
| 12 | Judge checks reply answers the question | Not e2e | – | Not built yet. API seam; nightly live suite. |
| 13 | Judge sees Remembered turns | Not e2e | – | Not built yet. API seam + spec 14 prompt contract test. |
| 14 | Judge sees given and cited Chunks | Not e2e | – | Not built yet. API seam / contract test. |
| 15 | Judge never sees system prompt | Not e2e | – | Not built yet. Prompt contract test. |
| 16 | Each check has one-sentence reason | Not e2e | – | Not built yet. Stored reasons tested at API seam; display covered by story 22 e2e. |
| 17 | Pass only when both checks pass | Not e2e | – | Not built yet. API seam. |
| 18 | Judge failure marked Error, excluded from Live score | Not e2e | – | Not built yet. API seam; Trace Error state via MSW. |
| 19 | Reply Purged before judging is skipped | Not e2e | – | Not built yet. API/task seam. |
| 20 | Reply, question, Chunks treated as data not instructions | Not e2e | – | Not built yet. Prompt contract test (spotlighting). |
| 21 | Live Verdicts use Organisation's Evaluation Model | Not e2e | – | Not built yet. API seam. |
| | **Seeing Live Verdicts** | | | |
| 22 | Live Verdict with both checks and reasons in Trace | Gap (high) | – | Not built yet. Planned in 15-07 (see Live Verdict in Conversations viewer Trace, axe on Trace section). |
| 23 | Trace shows 'Not judged' for unsampled replies | Gap (medium) | – | Not built yet. Planned MSW only; not in 15-07 e2e. |
| 24 | Filter Conversations viewer by Live Verdict | Gap (high) | – | Not built yet. Planned in 15-07 (filter to failed replies). |
| 25 | Conversation list shows failed-reply count | Gap (medium) | – | Not built yet. Planned MSW only; extend conversations.spec.ts. |
| 26 | Add failed reply to Evaluation Set | Gap (high) | – | Not built yet. Planned in 15-07; reuses flow in evaluation-loop.spec.ts. |
| 27 | Purge clears Verdict reasons, keeps pass/fail | Not e2e | – | Not built yet. Task seam (retention Purge tests). |
| 28 | Deleting Conversation clears Verdict reasons immediately | Not e2e | – | Not built yet. API seam. |
| | **Live score** | | | |
| 29 | Live score KPI card with Wilson interval and sample size | Gap (medium) | – | Not built yet. Planned MSW only; extend version-kpis.spec.ts. |
| 30 | Live score marked Low sample under 30 | Gap (low) | – | Not built yet. MSW planned; could join version-kpis.spec.ts. |
| 31 | Live score in Version comparison, higher is Better | Gap (medium) | – | Not built yet. MSW planned; not in 15-07; extend version-comparison.spec.ts. |
| 32 | Live score Time series metric with Live History markers | Gap (low) | – | Not built yet. MSW planned; extend time-series.spec.ts. |
| 33 | Only Visitor Conversations count toward Live score | Not e2e | – | Not built yet. API seam. |
| 34 | Live score unchanged across Purge | Not e2e | – | Not built yet. Task seam. |
| 35 | Live score column in comparison CSV export | Gap (low) | – | Not built yet. API seam; version-comparison.spec.ts already exports CSV and could assert column. |
| | **Live score drop alert** | | | |
| 36 | Alert when new Live Version's score clearly drops | Not e2e | – | Not built yet. Task seam (hourly alert check). |
| 37 | Alert waits for 30 Live Verdicts | Not e2e | – | Not built yet. Task seam. |
| 38 | Moderate ~10-point drops alert with enough data | Not e2e | – | Not built yet. Task seam. |
| 39 | Drops under 5 points never alert | Not e2e | – | Not built yet. Task seam. |
| 40 | One email with comparison and filtered-viewer links | Not e2e | – | Not built yet. Task seam with mailer outbox. |
| 41 | 'Live score drop' badge on Agent list and page | Gap (medium) | – | Not built yet. MSW planned only; needs seeded alert for e2e. |
| 42 | Alert clears when drop gone or new Version Live | Not e2e | – | Not built yet. Task seam. |
| | **Evaluation budget** | | | |
| 43 | Owner sets monthly Evaluation budget in Org settings | Gap (high) | – | Not built yet. 15-07 only axe-checks Org settings; no e2e of setting budget. |
| 44 | No budget by default; no sampling without one | Not e2e | – | Not built yet. API seam (setting rate without budget refused). |
| 45 | Spend meter in Org settings and Cost page | Gap (medium) | – | Not built yet. MSW planned; extend organisation-cost.spec.ts. |
| 46 | Sampling pauses org-wide when budget spent | Not e2e | – | Not built yet. API seam. |
| 47 | One email when budget is spent | Not e2e | – | Not built yet. API seam with mailer outbox. |
| 48 | Raising budget resumes sampling at once | Not e2e | – | Not built yet. API seam. |
| 49 | Budget resets monthly (UTC) | Not e2e | – | Not built yet. API seam with clock fake. |
| 50 | Visitor replies never affected by budget | Not e2e | – | Not built yet. API seam. |
| 51 | Editor-started Evaluation Runs never capped | Not e2e | – | Not built yet. API seam. |
| 52 | Budget changes recorded as Audit Events | Gap (low) | – | Not built yet. API seam only; could add to audit.spec.ts. |
| 53 | Live Verdict Cost in Org cost Evaluation column | Gap (medium) | – | Not built yet. API seam; extend organisation-cost.spec.ts. |
| 54 | Live Verdict Cost excluded from Token Budget and KPI cost | Not e2e | – | Not built yet. API seam. |
| | **Permissions, demo and accessibility** | | | |
| 55 | Editor can set Live sample rate | Gap (medium) | – | Not built yet. 15-07 sets rate but role unspecified; Editor permission untested in e2e. |
| 56 | Editor cannot change Evaluation budget | Gap (high) | – | Not built yet. API permission test + MSW read-only; no e2e planned. |
| 57 | Member sees Live Verdicts, score and badge | Gap (medium) | – | Not built yet. API permission tests only. |
| 58 | Other Organisations never see Live data or budget | Not e2e | – | Not built yet. API seam organisation isolation tests. |
| 59 | Demo: HR helper v2 Live score lower than v1 | Gap (medium) | – | Not built yet. Seed tests in 15-07 check data; no e2e of comparison UI. |
| 60 | New Trace section, filter, card, badge, settings accessible | Gap (medium) | – | Not built yet. 15-07 axe covers Trace section and Org settings only; filter, KPI card, badge not. |

<a id="spec-16"></a>
### 16 Spec 16: Suggestions

| # | Story | Status | E2E tests | Note |
|--:|---|---|---|---|
| | **Starting a Suggestion run** | | | |
| 1 | Suggestions tab in Agent's Evaluation view | Gap (high) | – | Not built yet. Planned in 16-07 (open seeded Suggestion; axe on Suggestions tab). |
| 2 | Choose UTC day range, default last 14 | Gap (medium) | – | Not built yet. MSW planned; 16-07 starts a run, default range likely. |
| 3 | See evidence counts by kind before starting | Gap (medium) | – | Not built yet. MSW planned only. |
| 4 | Warning under 10 evidence, still can start | Gap (low) | – | Not built yet. MSW planned only. |
| 5 | Estimated Cost shown before starting, proposing/checking split | Gap (high) | – | Not built yet. MSW planned only; money-related. |
| 6 | Run reads only current Live Version's replies | Not e2e | – | Not built yet. API seam. |
| 7 | Run refused for never-Published Agent with reason | Gap (medium) | – | Not built yet. API seam; UI refusal not in e2e. |
| 8 | At most one Suggestion run per Agent | Not e2e | – | Not built yet. API seam. |
| 9 | See run progress phases | Gap (medium) | – | Not built yet. 16-07 starts a run so will likely pass through progress; not asserted. |
| 10 | Cancel a run, keeping spend | Gap (medium) | – | Not built yet. Task/API seam; no e2e planned. |
| 11 | Suggestion run and Evaluate mutually exclusive | Not e2e | – | Not built yet. API seam. |
| | **Evidence** | | | |
| 12 | Failed Live Verdicts used as evidence | Not e2e | – | Not built yet. API seam. |
| 13 | Thumbs-down replies and comments as evidence | Not e2e | – | Not built yet. API seam. |
| 14 | Replies in 1-2 rated Conversations as evidence | Not e2e | – | Not built yet. API seam. |
| 15 | Failed Evaluation Cases from latest Run as evidence | Not e2e | – | Not built yet. API seam. |
| 16 | Reply Traces given to run | Not e2e | – | Not built yet. API seam / prompt contract test. |
| 17 | Purged replies excluded from evidence | Not e2e | – | Not built yet. API seam. |
| 18 | Evidence capped at 50 with count shown | Not e2e | – | Not built yet. API seam for cap; count display MSW. |
| | **The Suggestion** | | | |
| 19 | System prompt change shown as line Diff | Gap (high) | – | Not built yet. Planned in 16-07 (seeded Suggestion detail, apply). |
| 20 | Propose Top-k, Minimum Score, Hybrid changes | Not e2e | – | Not built yet. API seam (output validation); model quality in nightly live suite. |
| 21 | Retrieval changes cite their Traces | Gap (low) | – | Not built yet. API validation + MSW evidence chips; no e2e. |
| 22 | Each change has explanation and evidence links | Gap (medium) | – | Not built yet. MSW planned; 16-07 detail view may show it. |
| 23 | Suggested values within valid ranges | Not e2e | – | Not built yet. API seam (out-of-range rejected). |
| 24 | Knowledge Base gaps listed with evidence and link | Gap (medium) | – | Not built yet. Planned in 16-07 (see seeded gap). |
| 25 | Gaps-only Suggestion reads 'No configuration change' | Not e2e | – | Not built yet. API seam + MSW. |
| 26 | 'No change suggested' with reasoning is valid | Gap (low) | – | Not built yet. API/MSW only. |
| 27 | Suggestion never touches Instructions, model, Guardrails, etc. | Not e2e | – | Not built yet. API seam (unknown path rejected). |
| 28 | Explanation never quotes Visitors | Not e2e | – | Not built yet. Model behaviour; prompt/contract and live suite. |
| 29 | Visitor steering attempts treated as data | Not e2e | – | Not built yet. API seam with scripted model + contract test. |
| | **The check** | | | |
| 30 | Suggestion checked against Live on Evaluation Set | Gap (high) | – | Not built yet. Planned in 16-07 (see seeded check). |
| 31 | Both scores and Regressions with reasons shown | Gap (medium) | – | Not built yet. 16-07 sees seeded check; Regression detail likely MSW only. |
| 32 | Failed check is a warning, still applicable | Gap (medium) | – | Not built yet. MSW planned only. |
| 33 | 'Not checked' when no Evaluation Set | Gap (low) | – | Not built yet. MSW planned only. |
| 34 | No check when no configuration change | Not e2e | – | Not built yet. API seam. |
| 35 | Check Run in Run history labelled | Gap (low) | – | Not built yet. API/MSW only. |
| 36 | Check never counts in Publish Evaluation summary | Not e2e | – | Not built yet. API seam (Run excluded from summary). |
| | **Applying** | | | |
| 37 | Review Suggestion as Diff against current Draft | Gap (high) | – | Not built yet. Planned in 16-07 (apply flow). |
| 38 | Applying writes all changes in one save | Gap (high) | – | Not built yet. Planned in 16-07 (apply to Draft). |
| 39 | Unchanged Draft settings take suggested value | Not e2e | – | Not built yet. API seam (clean merge). |
| 40 | Apply refused on clashes, listing both values | Gap (high) | – | Not built yet. API + MSW only; data-loss guard with no e2e. |
| 41 | Stale-Draft conflict offers Load theirs / Save mine | Gap (high) | – | Not built yet. agent-drafts.spec.ts covers Draft editor conflict (16-01 prefactor must keep it passing); apply-flow conflict not in e2e. |
| 42 | Stale Suggestion applicable with old-Live warning | Gap (medium) | – | Not built yet. API + MSW only. |
| 43 | Applying never Publishes | Not e2e | – | Not built yet. API seam. |
| 44 | Draft Evaluation summary asks for new Run after apply | Gap (high) | – | Not built yet. Planned in 16-07 (Publish dialog asks for new Run). |
| 45 | Applied Suggestion marked with who and when | Gap (low) | – | Not built yet. MSW only. |
| 46 | Apply and delete recorded as Audit Events | Gap (low) | – | Not built yet. API seam only; could add to audit.spec.ts. |
| | **History and retention** | | | |
| 47 | Finished Suggestions listed with state, Cost, range | Gap (medium) | – | Not built yet. MSW; 16-07 sees list implicitly. |
| 48 | Delete a Suggestion | Gap (medium) | – | Not built yet. API/MSW only. |
| 49 | Evidence references Messages, never copies text | Not e2e | – | Not built yet. API seam (retention). |
| 50 | Purged evidence shown as 'Text purged' with date/verdict | Gap (medium) | – | Not built yet. Planned in 16-07 (seeded purged evidence). |
| 51 | Deleted Case evidence shown as 'Case deleted' | Gap (low) | – | Not built yet. API + MSW only. |
| | **Cost, permissions, demo and accessibility** | | | |
| 52 | Suggestion Cost frozen, in Org cost Evaluation column | Gap (medium) | – | Not built yet. API seam; extend organisation-cost.spec.ts. |
| 53 | Suggestion runs not capped by Evaluation budget | Not e2e | – | Not built yet. API seam. |
| 54 | Suggestion runs use Evaluation Model | Not e2e | – | Not built yet. API seam. |
| 55 | Editor can start, cancel, apply, delete | Gap (high) | – | Not built yet. 16-07 covers start and apply; cancel, delete and Editor role not. |
| 56 | Member can read Suggestions | Gap (medium) | – | Not built yet. API permission tests only. |
| 57 | Archived Agent's Suggestions readable, runs/apply refused | Gap (medium) | – | Not built yet. API seam; agent-archive.spec.ts could extend. |
| 58 | Permanent deletion removes Suggestions | Not e2e | – | Not built yet. API seam. |
| 59 | Other Organisations never see Suggestions | Not e2e | – | Not built yet. API organisation isolation tests. |
| 60 | Demo: seeded Suggestion with check, gap, purged evidence | Gap (medium) | – | Not built yet. Planned in 16-07 (e2e + seed tests). |
| 61 | Tab, dialog, detail, apply flow accessible | Gap (medium) | – | Not built yet. 16-07 axe covers tab and detail; run dialog and apply flow not. |

## Tests mapped to stories

Each Playwright file and the stories its tests cover or partly cover. The harness files test the suite's own fixtures against a fake Studio.

| File | Tests | Stories |
|---|--:|---|
| `tests/accessibility.spec.ts` | 1 | 01.42, 02.33, 11.3, 11.33, 12.83 |
| `tests/agent-archive.spec.ts` | 1 | 04.1, 04.2, 04.3, 04.34, 04.35, 04.36 |
| `tests/agent-config.spec.ts` | 1 | 02.13, 04.7, 04.8, 04.17, 04.20, 04.21, 04.22, 04.24, 04.37, 08.4, 11.19, 13.1, 13.2, 13.3, 13.4, 13.7, 13.8, 13.45 |
| `tests/agent-drafts.spec.ts` | 1 | 04.22, 05.8, 05.10, 05.11, 05.15, 05.16, 05.17, 05.33, 11.22, 13.45 |
| `tests/agent-publish.spec.ts` | 1 | 04.3, 05.1, 05.2, 05.3, 05.4, 05.5, 05.18, 05.33, 12.70 |
| `tests/agent-revert.spec.ts` | 1 | 05.1, 05.3, 05.4, 05.5, 05.8, 05.9, 05.12, 05.14, 05.18, 05.33 |
| `tests/attack-panel.spec.ts` | 4 | 08.11, 08.12, 08.25, 10.18 |
| `tests/audit.spec.ts` | 1 | 01.39, 01.40 |
| `tests/auth.spec.ts` | 5 | 01.11, 01.12, 01.13, 01.14, 01.15, 01.17, 01.42 |
| `tests/bedrock-credentials.spec.ts` | 1 | 02.4, 02.5, 02.6, 02.7, 02.8, 02.11, 02.15 |
| `tests/branded-widget.spec.ts` | 1 | 02.22, 02.26, 02.27, 02.30, 04.17, 04.18, 06.2, 06.13, 06.14, 06.15, 06.16, 06.17, 06.28, 11.35 |
| `tests/bulk-rollout.spec.ts` | 1 | 05.4, 05.12, 05.13, 05.19, 05.20, 05.21, 05.22, 05.23, 05.25, 05.27, 05.28, 05.29, 05.33 |
| `tests/conversation-rating.spec.ts` | 1 | 04.19, 06.22, 07.4, 07.5, 07.6, 07.7, 07.8, 07.9 |
| `tests/conversations.spec.ts` | 1 | 04.31, 05.32, 07.9, 07.10, 11.26, 11.27, 12.72 |
| `tests/credentials.spec.ts` | 2 | 02.2, 02.3, 02.7, 02.8, 02.9, 02.10, 02.11, 02.12, 02.13, 02.15, 02.16, 02.21, 02.33 |
| `tests/demo-pages.spec.ts` | 4 | 06.14, 06.15, 06.23, 06.31, 06.35, 10.5, 10.16, 10.17, 10.19 |
| `tests/document-editions.spec.ts` | 1 | 03.15, 03.16, 03.17, 03.18 |
| `tests/documents.spec.ts` | 3 | 03.3, 03.11, 03.12, 03.22, 03.23, 03.24, 03.25, 03.26, 08.13, 08.14, 08.15, 11.17, 11.18, 12.49, 12.55 |
| `tests/embed.spec.ts` | 1 | 06.1, 06.2, 06.3, 06.4, 06.6, 06.14, 06.18, 06.19, 08.3, 08.5, 11.23, 12.72 |
| `tests/embedding-models.spec.ts` | 2 | 02.3, 02.13, 02.14, 03.28, 03.29, 03.30, 03.31, 03.35, 12.49, 12.50, 12.51, 12.52 |
| `tests/evaluation-loop.spec.ts` | 1 | 14.1, 14.5, 14.15, 14.17, 14.19, 14.24, 14.25, 14.36, 14.39, 14.41, 14.50, 14.51, 14.52, 14.70, 14.75, 14.76 |
| `tests/five-minute-demo.spec.ts` | 1 | 05.9, 06.31, 06.35, 07.11, 07.16, 07.33, 08.12, 08.13, 08.25, 10.5, 10.9, 10.11, 10.13, 10.14, 10.16, 10.17, 10.18, 10.19, 10.20, 13.22, 13.26, 13.41, 13.42, 14.1, 14.6, 14.39, 14.41, 14.42, 14.48, 14.75, 14.76 |
| `tests/guardrail-analytics.spec.ts` | 1 | 07.9, 07.18, 08.3, 08.17, 08.18, 11.27 |
| `tests/ingestion-failures.spec.ts` | 1 | 03.9, 03.12, 03.13, 03.14, 03.34 |
| `tests/instructions-versions.spec.ts` | 1 | 05.2, 05.19, 05.27, 05.30, 05.33 |
| `tests/instructions.spec.ts` | 1 | 04.5, 04.23, 04.36 |
| `tests/invites.spec.ts` | 2 | 01.27, 01.28, 01.29, 01.30, 01.31, 01.37, 01.39, 12.36, 12.37, 12.38, 12.39, 12.60 |
| `tests/llm-classifier.spec.ts` | 1 | 04.20, 08.5, 08.8, 08.9, 08.16 |
| `tests/members.spec.ts` | 2 | 01.12, 01.33, 01.34, 01.35, 01.36, 01.37, 01.38, 01.39, 01.41, 11.11 |
| `tests/message-feedback.spec.ts` | 1 | 05.32, 07.1, 07.2, 07.3, 07.8, 07.9, 07.10 |
| `tests/mfa.spec.ts` | 2 | 01.21, 01.22, 01.23, 01.24 |
| `tests/models.spec.ts` | 1 | 02.1, 02.3, 02.13, 02.14, 02.17, 02.18, 02.21, 02.33, 13.11 |
| `tests/ocr.spec.ts` | 1 | 03.27, 12.49, 12.54 |
| `tests/operational-settings.spec.ts` | 1 | 04.18, 06.4, 06.5, 06.6, 06.7, 06.11, 06.12, 06.23, 06.35, 11.24 |
| `tests/organisation-cost.spec.ts` | 1 | 04.32, 07.33, 12.27, 12.30, 12.31, 14.68 |
| `tests/organisation-switcher.spec.ts` | 1 | 01.32, 01.37, 11.7, 12.60 |
| `tests/password-reset.spec.ts` | 4 | 01.13, 01.17, 01.18, 01.19, 01.20, 01.43 |
| `tests/playground-errors.spec.ts` | 1 | 04.29, 04.33, 11.31 |
| `tests/playground-instructions.spec.ts` | 1 | 05.31, 05.32 |
| `tests/playground.spec.ts` | 3 | 04.1, 04.4, 04.5, 04.6, 04.10, 04.20, 04.21, 04.22, 04.24, 04.25, 04.26, 04.27, 04.30, 07.11, 08.3, 08.4, 08.5, 08.6, 08.7, 08.11, 08.12, 08.16, 11.20, 13.2, 13.10, 13.11, 13.12, 13.22, 13.26, 13.27 |
| `tests/prices.spec.ts` | 1 | 02.1, 02.19, 02.20, 02.21 |
| `tests/project-deletion.spec.ts` | 1 | 03.7, 03.35, 11.13, 11.15, 12.11, 12.14 |
| `tests/projects.spec.ts` | 2 | 03.1, 03.3, 03.4, 03.5, 03.6, 03.35, 03.36, 11.13, 11.16, 11.31, 12.2, 12.3, 12.4, 12.7, 12.9, 12.10, 12.11, 12.14, 12.15, 12.16, 12.18, 12.22, 12.24 |
| `tests/rate-limits.spec.ts` | 1 | 06.8, 06.11, 06.23, 06.34 |
| `tests/require-mfa.spec.ts` | 1 | 01.24, 01.25, 01.26, 01.28, 01.39, 12.69 |
| `tests/reranker.spec.ts` | 1 | 04.11, 04.13, 04.15, 04.28, 04.37 |
| `tests/retention.spec.ts` | 2 | 07.12, 07.27, 07.30, 07.32, 11.15 |
| `tests/seed.spec.ts` | 3 | 10.5, 10.7, 10.8, 10.10, 13.41, 13.43 |
| `tests/select-chevron.spec.ts` | 1 | 12.42, 12.43, 12.44, 12.45 |
| `tests/sidebar.spec.ts` | 4 | 01.42, 11.6, 11.7, 11.8, 11.9, 11.12, 11.32, 11.34, 12.58, 12.59, 12.61, 12.62, 12.64, 12.65, 12.66, 12.67, 12.68, 12.71, 12.74, 12.76, 12.77, 12.78, 12.79, 12.80, 12.81 |
| `tests/smoke.spec.ts` | 2 | 01.1 |
| `tests/tag-scoping.spec.ts` | 1 | 04.14, 04.28 |
| `tests/tags.spec.ts` | 1 | 03.8, 03.19, 03.20, 03.21, 11.18 |
| `tests/theme.spec.ts` | 4 | 02.22, 02.25, 02.27, 02.28, 02.29, 02.30, 02.31, 02.32, 02.33, 11.35 |
| `tests/time-series.spec.ts` | 1 | 07.22, 07.25, 11.29, 11.30 |
| `tests/token-budget.spec.ts` | 1 | 04.31, 06.9, 06.10, 06.11, 06.23, 06.31, 06.32, 06.34, 11.25, 13.30, 13.31 |
| `tests/version-comparison.spec.ts` | 1 | 07.16, 07.20, 07.21, 07.23, 07.26, 11.21, 13.5, 13.32, 13.33 |
| `tests/version-kpis.spec.ts` | 1 | 04.31, 07.1, 07.5, 07.13, 07.14, 07.16, 07.17, 07.18, 07.19, 07.24, 11.28, 13.32, 13.33 |
| `tests/widget-accessibility.spec.ts` | 2 | 06.14, 06.16, 06.18, 06.25, 06.26, 06.27, 13.23, 13.24 |
| `tests/widget-lifecycle.spec.ts` | 3 | 06.20, 06.21, 06.22, 06.24 |
| `harness/agent-navigation.spec.ts` | 2 | *none* |
| `harness/auth.spec.ts` | 5 | *none* |
| `harness/axe.spec.ts` | 2 | *none* |
| `harness/drawer.spec.ts` | 2 | *none* |
| `harness/navigation.spec.ts` | 6 | *none* |
| `harness/stack.spec.ts` | 3 | *none* |
