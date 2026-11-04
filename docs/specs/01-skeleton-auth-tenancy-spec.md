# Spec 01: Skeleton, CI, auth and tenancy

## Problem Statement

Nothing exists yet. Before anyone can build Agents, a person needs a safe way to get into the Studio, create an Organisation, and bring colleagues in with the right permissions. Developers also need a foundation that keeps every later slice honest: a runnable local stack, a typed API contract shared by backend and frontend, and CI that refuses to merge anything below 100% line and branch coverage. Since the product will store customers' model API keys, account security has to be credible from day one.

## Solution

A monorepo that starts with one command:
- a FastAPI backend, a Celery worker and Beat, and a React Studio, with the API client generated from the backend's OpenAPI schema;
- every CI workflow in place and green;
- Terraform modules stubbed so infrastructure linting already passes.

Signing up creates an Organisation with the new Member as its Owner. Owners invite colleagues by email (or by copyable link), assign Owner or Editor roles, and can require TOTP MFA for everyone in the Organisation. Members can belong to several Organisations and switch between them. Sign-in is rate limited, passwords can be reset by email, and every membership and security change is recorded as an Audit Event that Owners can browse.

## User Stories

1. As a developer, I want one command to start Postgres, Redis, RustFS, Mailpit, the API, the worker, Beat and the Studio, so that I can run the whole product locally.
2. As a developer, I want a single `make` entry point for dev, test, lint, client generation and end-to-end runs, so that I don't need to remember tool-specific commands.
3. As a developer, I want configuration loaded and validated from environment variables at startup, so that a misconfigured service fails fast with a clear message.
4. As a developer, I want the frontend API client generated from the backend's OpenAPI schema, so that frontend and backend can't silently drift apart.
5. As a developer, I want CI to fail when the generated client is out of date, so that contract drift is caught in review.
6. As a developer, I want CI to fail below 100% line and branch coverage on backend and frontend, so that the coverage promise is enforced, not aspirational.
7. As a developer, I want CI to run lint, type checks, tests, dependency audits, secret scanning and image scanning, so that quality and security gates exist before features arrive.
8. As a developer, I want Terraform linting and policy checks running on stub modules from the start, so that infrastructure quality is enforced from slice 1.
9. As a developer, I want database migrations tested by an upgrade/downgrade round trip, so that migrations can be excluded from coverage without going untested.
10. As a developer, I want telemetry to scrub Message text and secrets, with a test proving it, so that observability never becomes a data leak.
11. As a visitor to the Studio, I want to sign up with my name, email, password and Organisation name, so that I can start using the product without talking to anyone.
12. As a new Member, I want signing up to make me the Owner of a new Organisation, so that I can configure it immediately.
13. As a Member, I want to sign in with email and password, so that I can reach my Organisations.
14. As a Member, I want my session held in a secure httpOnly cookie, so that scripts on the page can't steal it.
15. As a Member, I want to sign out, so that a shared computer doesn't stay signed in.
16. As a Member, I want repeated failed sign-ins to be slowed and then temporarily locked out, so that my password can't be brute-forced.
17. As a Member, I want sign-in errors that don't reveal whether an email is registered, so that attackers can't enumerate accounts.
18. As a Member who forgot my password, I want to request a reset link by email, so that I can regain access.
19. As a Member, I want reset links to expire and work only once, so that an old email can't be used to take over my account.
20. As a Member, I want resetting my password to end my other sessions, so that an attacker who had access is cut off.
21. As a Member, I want to enrol TOTP MFA with an authenticator app by scanning a QR code, so that my account is protected beyond my password.
22. As a Member, I want one-time recovery codes when I enrol in MFA, so that losing my phone doesn't lock me out forever.
23. As a Member with MFA, I want to be asked for a code after my password, so that a stolen password alone is not enough.
24. As a Member, I want to disable MFA only after re-confirming my password and a code, unless my Organisation requires it, so that MFA can't be switched off by someone who walked up to my session.
25. As an Owner, I want to require MFA for every Member of my Organisation, so that the Provider Credentials we store are better protected.
26. As a Member of an Organisation that requires MFA, I want to be guided through enrolment the next time I open it, so that I'm compliant without hunting for settings.
27. As an Owner, I want to invite a colleague by email with a chosen role, so that they can join my Organisation.
28. As an Owner, I want to copy an invite link instead of relying on email, so that I can onboard people even before email delivery is configured.
29. As an invited person without an account, I want the invite link to let me create an account and join in one flow, so that onboarding is quick.
30. As an existing Member, I want accepting an invite to add the Organisation to my account, so that I can belong to several Organisations with one login.
31. As an Owner, I want invites to expire, and to be able to revoke a pending invite, so that stale links can't be used.
32. As a Member of several Organisations, I want an Organisation switcher, so that I can move between them without signing out.
33. As an Owner, I want to see every Member with their role, so that I know who has access.
34. As an Owner, I want to change a Member's role between Owner and Editor, so that permissions follow responsibilities.
35. As an Owner, I want to remove a Member, so that people who leave lose access immediately.
36. As an Owner, I want to be prevented from removing or demoting the last Owner, so that an Organisation can never be left unmanageable.
37. As an Editor, I want Owner-only areas hidden and refused by the API, so that the permission model can't be bypassed through the UI or by calling the API directly.
38. As a Member, I want to leave an Organisation, unless I'm its last Owner, so that I control my own memberships.
39. As an Owner, I want every invite, role change, removal, MFA policy change and security event recorded as an Audit Event with who, what, when and before/after values, so that I can investigate changes.
40. As an Owner, I want an Audit tab I can filter by actor, action and date, so that I can find a specific event quickly.
41. As an Editor, I want the Audit tab hidden from me, so that audit data stays with Owners.
42. As a Member, I want a clean, minimal Studio shell with navigation for Projects and Organisation settings, so that the product feels coherent before features fill it.
43. As a Member, I want to edit my profile name and change my password, so that my account details stay current.

## Implementation Decisions

- **Repository.** A monorepo with a backend Python project (uv, Python 3.13, ruff, strict mypy), a pnpm frontend workspace (Studio app, widget app placeholder, shared UI package, generated API client package; Node 22 LTS), and an infrastructure folder with stub modules. Layout as in the plan.
- **Settings.** Every service setting is a typed Pydantic Settings model read from the environment. Adapter selection (real or fake: mailer, key wrapper, object store, and later the models) is driven by settings.
- **Persistence.** SQLAlchemy 2 (async) with Alembic. Every table below the platform level carries an `organisation_id`. Data access goes through repository functions that require the Organisation in scope; there is no unscoped query path for tenant data.
- **Authentication module.** A deep module with a small interface: sign up, sign in, verify MFA, sign out, request and complete a password reset, enrol, confirm and disable MFA, and resolve the current Member from a request. Internals:
  - argon2id password hashes;
  - server-side sessions stored in Redis, referenced by an opaque httpOnly, Secure, SameSite=Lax cookie;
  - sessions rotated on privilege change;
  - "sign out other sessions" on password reset.
- **Sign-in protection.** Redis counters per account and per IP, giving progressive delay and then a temporary lockout. Responses are uniform so accounts can't be enumerated.
- **MFA.** RFC 6238 TOTP with a ±1 step window. The secret is encrypted with the same envelope-encryption service introduced in spec 02; in this slice, the local key wrapper. There are ten single-use recovery codes, stored hashed. A sign-in that needs MFA returns a short-lived "MFA pending" state rather than a full session.
- **Tenancy module.** Organisations, memberships with roles (Owner, Editor), invites with an expiry and a single-use token stored hashed, the last-Owner invariant, and the Organisation switcher context. The active Organisation is part of the request path for every Organisation-scoped API route.
- **Authorisation.** A single policy dependency declares the required role per route. Editor-forbidden routes return 403. Routes in another tenant return 404, so the API never reveals that a resource exists elsewhere.
- **Mailer port.** A send-templated-email interface with an SES adapter (unused until a domain exists), a Mailpit SMTP adapter for local development and a fake outbox for tests. Invite and reset emails always have an equivalent copyable link for Owners.
- **Audit module.** One `record` operation taking the actor, Organisation, action, target, and before/after values, with fields matching a secret-like pattern redacted. It writes to an append-only Audit Event table, and there is a filterable, paginated list endpoint for Owners. Later specs reuse this module.
- **Telemetry.** OpenTelemetry through the Logfire SDK, exporting to Logfire when a token is set and to the console otherwise. FastAPI, SQLAlchemy, Celery and HTTP clients are instrumented automatically. A scrubbing processor removes request bodies containing Message content, cookies, authorisation headers and secret-like attributes.
- **API contract.** OpenAPI is generated from FastAPI, and the TypeScript client is generated from it. A drift check regenerates the client and compares it with the committed copy.
- **Studio shell.** Vite, React 19, TanStack Router and Query, Tailwind and shadcn/ui. Screens: sign up, sign in, MFA challenge, forgot and reset password, accept invite, Organisation switcher, Members, Audit, Profile. Projects is a placeholder.
- **CI workflows.** `backend`, `frontend`, `e2e`, `guardrails-eval` (placeholder that passes), `infra`, `security`, `deploy` (image build only; nothing is deployed without AWS secrets). All are created in this slice, as described in plan section 6.
- **Celery wiring.** Worker and Beat processes start with a health-check task, so later slices only add tasks.

## Testing Decisions

- **What a good test is:** it exercises behaviour a Member or developer can observe, such as HTTP responses, emails in the outbox, cookies, and Audit Events listed through the API. It doesn't assert on private functions, ORM internals or component state.
- **API seam** for all auth, tenancy and audit behaviour. Scenarios:
  - sign-up → sign-in → MFA enrolment → MFA challenge;
  - lockout after repeated failures, then recovery with the controllable clock;
  - reset-link expiry and single use;
  - invite accept for both new and existing accounts;
  - the last-Owner invariant;
  - role-based 403s, and cross-tenant 404s for every Organisation-scoped route, using a shared parametrised isolation test that later specs extend.
- **Adapter fakes:** mailer outbox, local key wrapper, controllable clock.
- **Telemetry scrubbing:** a test captures exported spans with an in-memory exporter and asserts that no Message-like body, cookie or secret appears.
- **Migrations:** an upgrade-to-head / downgrade-to-base round-trip test.
- **Frontend, network seam:** each Studio screen's happy path and error states. For example: wrong password, lockout message, invalid MFA code, expired invite, last-Owner refusal, and Editor not seeing Owner navigation.
- **End-to-end seam:** sign up → invite an Editor → open the invite email in Mailpit → accept → Editor signs in → Owner requires MFA → Editor is forced to enrol.
- **Prior art:** none yet. This slice *establishes* the test fixtures (app client, tenant factory, signed-in client per role, mailer outbox, clock) that every later spec reuses.

## Out of Scope

- SSO or social login.
- A session-list UI or per-device sign-out.
- Deleting Organisations.
- Sending SES email in AWS. The adapter is built; it's switched on when a domain exists.
- Projects, Agents and every other feature area beyond navigation placeholders.
- Real Terraform resources (only stubs that pass linting).

## Further Notes

- The last-Owner invariant and cross-tenant 404s are worth demoing in interviews. Keep the parametrised isolation test easy to extend.
- WebAuthn and passkeys are an obvious next step after TOTP, but not now.
- ADR-0005 (hand-rolled auth) and ADR-0008 (coverage) govern this slice.
