# Spec 10: Seed data and showcase

## Problem Statement

This project exists to be shown in interviews, often in a short slot with someone who has never seen it. An empty Studio shows nothing. The interviewer needs to see a realistic Organisation with Documents, Agents with real Version history, analytics with actual numbers, an Agent embedded on a "customer" website, and the Guardrails stopping attacks, all within minutes of cloning or opening the demo URL. Engineers reviewing the code need a README that explains what it is, how it's built and why, and points to the decisions.

## Solution

A single `make seed` command fills a fresh environment (local or the AWS demo) with a believable demo Organisation:
- an Owner and an Editor;
- a "Northwind Handbook" Project with Tags and a handful of synthetic Documents, including one planted with an indirect-injection Chunk;
- two Agents (an internal HR helper and a public product FAQ) with three Versions of history and Project Instructions with two Versions;
- several weeks of synthetic Conversations, feedback and ratings, so the comparison charts tell a story.

The repository also ships:
- a static demo host page that embeds the public Agent;
- a page on a disallowed origin that proves framing is blocked;
- an attack panel that fires sample attacks and shows which Guardrail layer stopped each one;
- a README with the pitch, an architecture diagram, a five-minute demo script, the ADR index, and instructions for running locally and deploying.

## User Stories

1. As a developer, I want `make dev && make seed` on a fresh clone to give me the full demo in under five minutes, so that preparing for an interview is effortless.
2. As a developer, I want seeding to be idempotent, so that running it twice doesn't duplicate data.
3. As a developer, I want `make seed-reset` to wipe and recreate the demo Organisation only, so that I can restore a clean demo after experimenting.
4. As a developer, I want the seed to run against the AWS demo environment through a one-off ECS task, so that the cloud demo looks the same as local.
5. As a developer, I want the seed to work without any real Provider Credential, using the fake chat model and the local Embedding Model, so that the demo needs no API keys.
6. As a developer, I want seeding to also accept a real Provider Credential from the environment, so that I can demo real answers when I have a key.
7. As an interviewer, I want to sign in as a demo Owner or Editor with credentials printed by the seed and shown on the README, so that I can explore both roles.
8. As an interviewer, I want the demo Project to contain realistic Documents (a staff handbook, a product FAQ, a returns policy, a slide deck) that are synthetic and freely licensed, so that answers look real without using anyone's real data.
9. As an interviewer, I want one Document to contain a planted instruction that's flagged in the viewer, so that I can see indirect-injection detection.
10. As an interviewer, I want Tags splitting HR and product content, with each Agent scoped accordingly, so that I can see one Project serving two audiences.
11. As an interviewer, I want the HR Agent to have three Versions where v2 made things worse and was reverted, visible in its Live History, so that versioning and revert tell a story.
12. As an interviewer, I want Project Instructions with two Versions and one Agent "behind", so that pinned Instructions and bulk adoption are visible.
13. As an interviewer, I want several weeks of synthetic Conversations with feedback, ratings, token usage and some Guardrail blocks, distributed so that the comparison shows a clear but honest difference with confidence intervals, so that analytics are meaningful.
14. As an interviewer, I want a small-sample Version included, so that I can see the "low confidence" treatment.
15. As an interviewer, I want an Organisation Theme with a distinctive brand and a per-Agent override, so that branding is obviously applied.
16. As an interviewer, I want a demo host website (a fictional shop page) with the public Agent embedded as a bubble, and another page with the inline layout, so that I can experience it as a Visitor would.
17. As an interviewer, I want a page on a different, disallowed origin that tries to embed the Agent and visibly fails, so that I can see Allowed Origins enforcement.
18. As an interviewer, I want an attack panel with one-click attacks (instruction override, prompt extraction, role-play jailbreak, encoded attack, benign control) that shows the response and which Guardrail layer acted, so that I can see the defences work.
19. As an interviewer, I want a low Token Budget on one demo Agent that a button can exhaust, so that I can see the graceful unavailable state and the Studio alert.
20. As an interviewer, I want Audit Events already populated from the seeded history, so that the Audit tab isn't empty.
21. As a reviewer, I want a README that explains the product in two sentences, shows an architecture diagram, lists the stack, and links the glossary, ADRs, plan and specs, so that I can orient myself quickly.
22. As a reviewer, I want a five-minute demo script in the README, so that I see the highlights in a sensible order.
23. As a reviewer, I want README sections on testing strategy (100% coverage, seams, evaluation suite) and security (envelope encryption, Guardrails, embed protections), so that the engineering depth is easy to find.
24. As a reviewer, I want badges for CI status and coverage, so that quality is visible at a glance.
25. As a developer, I want README instructions for deploying to and destroying the AWS demo, with the expected cost, so that I can run it in the cloud responsibly.

## Implementation Decisions

- **Seed module.** A backend command that uses the platform's own application services (sign-up, Project creation, upload and ingestion, Agent publishing, widget Conversation APIs) rather than writing tables directly, except for backfilling historical timestamps. This keeps seeded data valid by construction. It's idempotent: it looks up the demo Organisation by a fixed slug, and reset deletes and recreates that Organisation only.
- **Historical data.** Conversations are generated through the real runtime path, using a seeded `FunctionModel` that produces plausible answers from the retrieved Chunks. The seed then rewrites their timestamps across the past several weeks, applies feedback and ratings from a fixed random seed with Version-specific probabilities (v2 noticeably worse), and runs the rollup task for each historical day. The controllable clock is used during generation.
- **Content.** Synthetic Documents (markdown converted to PDF, DOCX and PPTX at build time, with outputs committed) live in a seed assets folder with a licence note. One contains an injection payload in a footnote.
- **Demo host pages.** Static HTML served by a small static server in `docker compose` on two extra ports: an allowed shop origin and a disallowed origin. In AWS, the demo pages are uploaded to the static bucket under a `/demo/` path, and the disallowed-origin demo is documented as local-only.
- **Attack panel.** A static page using the demo/seed-mode debug endpoint (spec 08) to send fixed attack payloads and render the stream and Trace outcome. It's only enabled when the environment flag for demo mode is on.
- **Fake model in compose.** When no real credential is configured, the demo Organisation's credential uses a "demo" provider adapter backed by the deterministic `FunctionModel`, visibly labelled as a demo model in the Studio, so nobody mistakes it for a real model.
- **README.** Pitch, screenshot or GIF, architecture diagram (Mermaid), stack list, quickstart, five-minute demo script, links to `GLOSSARY.md` / `docs/adr` / `docs/plan.md` / `docs/specs`, testing strategy, security model, deploy and destroy with cost, licence.

## Testing Decisions

- **Good tests** run the seed against a fresh test database and assert what an interviewer would see through the API: the demo Organisation exists, both Agents are Live at the expected Versions, Live History shows the revert, Instructions show one Agent behind, analytics return the intended v1/v2/v3 ordering with intervals, the flagged Chunk exists, and Audit Events are present.
- **Idempotence:** running the seed twice yields the same counts. Reset recreates the demo Organisation and leaves any other Organisation untouched.
- **Demo provider adapter:** tested through the model gateway like any provider adapter.
- **End-to-end:** after `make seed`, Playwright:
  1. signs in as the demo Owner and opens the comparison;
  2. visits the shop page and chats through the widget;
  3. checks the disallowed-origin page is blocked;
  4. clicks each attack-panel button and asserts the expected layer outcome;
  5. exhausts the low budget and sees the unavailable state.
  This is the "five-minute demo" automated.
- **README links:** a CI job checks that every relative link in the README and docs resolves.
- **Prior art:** every previous spec's end-to-end tests. This spec's end-to-end test joins them into the narrative.

## Out of Scope

- Real customer data or real company names and brands. All content is synthetic.
- Multiple demo Organisations.
- A hosted, always-on public demo (the AWS demo is applied on demand, per spec 09).
- Video production for the README (a GIF is enough).

## Further Notes

- Tune the synthetic feedback probabilities so the comparison is clearly visible but not cartoonish. The confidence intervals should overlap for the small-sample Version.
- The demo script order: the Studio, the Knowledge Base viewer with the flagged Chunk, the Agent editor and Playground Trace, publish and revert, the embed on the shop page, the disallowed origin, the attack panel, analytics comparison, the Audit tab.
