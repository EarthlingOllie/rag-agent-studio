# Spec 02: Provider Credentials and Theme

## Problem Statement

An Organisation can't run Agents until it can safely tell the platform how to reach a model provider, and different teams have different providers. One team has an Anthropic key, another has an AWS account with Bedrock, a third wants OpenAI. Handing an API key to a SaaS product is a trust decision: Owners need to know the key is encrypted, never shown again, checked when it's saved, and auditable.

Separately, an Organisation that embeds an Agent on its website needs that Agent to look like part of its brand, not like a third-party widget. It needs to set the look once and see it before any Visitor does.

## Solution

Owners manage Provider Credentials for Anthropic, OpenAI, Bedrock and Voyage:
- Each credential is encrypted with envelope encryption, checked with a live call when saved, shown only as a masked suffix, and can be rotated or deleted.
- Each credential declares what it can do (chat, embeddings or both), so later model pickers only offer valid choices.
- Bedrock accepts either a cross-account IAM role (preferred, since no secret is stored) or access keys.

Owners choose a Default Model for the Organisation, and can override the platform price table per credential so cost reporting reflects negotiated rates.

Owners also design the Organisation's Theme: colour tokens, corner radius, a font from a curated list, logo, light/dark/auto mode, launcher type and position. A live preview shows the result, and a warning appears if any colour pair fails accessible contrast.

## User Stories

1. As an Owner, I want to add an Anthropic credential with an API key, so that Agents can use Claude models.
2. As an Owner, I want to add an OpenAI credential with an API key, so that Agents can use OpenAI chat models and OpenAI embeddings.
3. As an Owner, I want to add a Voyage credential, so that Projects can use Voyage embeddings and reranking.
4. As an Owner, I want to add a Bedrock credential by giving a role ARN that the platform assumes with an external ID, so that I grant access without handing over a long-lived secret.
5. As an Owner, I want the Studio to show me the external ID and the trust policy to paste into my AWS account, so that setting up the role is straightforward.
6. As an Owner, I want to add a Bedrock credential with an access key, secret and region as a fallback, so that I can use Bedrock in environments where role assumption isn't possible.
7. As an Owner, I want each credential checked with a live call when I save it, so that I learn about typos or missing permissions immediately rather than when a Visitor asks a question.
8. As an Owner, I want a clear reason when the check fails (invalid key, missing model access, wrong region, role not assumable), so that I can fix it without contacting support.
9. As an Owner, I want to name each credential, so that I can tell "Marketing OpenAI" from "Legal OpenAI".
10. As an Owner, I want to see each credential's provider, capabilities, masked suffix and last-checked time, so that I know what's configured without seeing secrets.
11. As an Owner, I want to re-run the check on demand, so that I can confirm a credential still works after changes in my provider account.
12. As an Owner, I want to rotate a credential's secret without changing its identity, so that Agents using it keep working through a key rotation.
13. As an Owner, I want to delete a credential, and be told which Agents or Projects still reference it, so that I don't break things by accident.
14. As an Owner, I want deletion blocked while something still depends on the credential, so that a live Agent can't lose its model unexpectedly.
15. As an Owner, I want the API never to return a secret after it's saved, so that a compromised Studio session can't exfiltrate keys.
16. As an Editor, I want to see which credentials exist (name, provider, capabilities) without managing them, so that I can choose models for my Agents.
17. As an Owner, I want to set the Organisation's Default Model by choosing a chat-capable credential and one of its models, so that new Agents work without extra setup.
18. As an Owner, I want the model list for a credential limited to models that provider supports for that capability, so that I can't pick an embeddings model for chat.
19. As an Owner, I want to see the platform price for each model, so that I understand what cost reports are based on.
20. As an Owner, I want to override input, output and cached-token prices per credential, so that negotiated Bedrock or enterprise rates show up in cost reporting.
21. As an Owner, I want every credential create, rotate, check failure, delete, Default Model change and price override recorded as an Audit Event, without the secret, so that sensitive changes are traceable.
22. As an Owner, I want to set the Theme's primary, surface, text and accent colours, so that embedded Agents match our brand.
23. As an Owner, I want to set the corner radius, so that the widget matches our design language.
24. As an Owner, I want to choose a font from a curated list, so that the widget's text matches our site without loading arbitrary font URLs.
25. As an Owner, I want to upload a logo and a default Agent avatar, so that Visitors recognise who they're talking to.
26. As an Owner, I want to choose light, dark or automatic mode, so that the widget suits our site and our Visitors' preferences.
27. As an Owner, I want to choose a floating bubble launcher or an inline container, and the bubble's corner, so that the Agent fits our page layout.
28. As an Owner, I want a live preview of the widget as I edit the Theme, so that I see exactly what Visitors will see.
29. As an Owner, I want a warning when text and background colours fail WCAG AA contrast, so that I don't publish an inaccessible widget by mistake.
30. As an Owner, I want Theme changes to apply as soon as I save them, without publishing anything, so that branding fixes go out immediately.
31. As an Owner, I want Theme changes recorded as Audit Events, so that I can see who changed our branding.
32. As an Editor, I want to view the Theme but not change it, so that branding stays under Owner control.
33. As a Member, I want the Credentials, Default Model and Theme pages to be clean and self-explanatory, so that setup feels effortless.

## Implementation Decisions

- **Envelope encryption module.** A deep module with two operations: seal (plaintext → sealed record of ciphertext, wrapped data key, key ID, algorithm) and open (sealed record → plaintext). AES-256-GCM, with a fresh data key per record. Behind it, a key-wrapper port: an AWS KMS adapter and a local static-key adapter. The sealed format is versioned so it can be rotated. TOTP secrets from spec 01 move onto this module if they weren't already (ADR-0006).
- **Provider Credential model.** Name, provider (Anthropic, OpenAI, Bedrock, Voyage), auth kind (API key, AWS role, AWS access keys), sealed secret, region where relevant, masked suffix, capabilities (chat and/or embeddings, plus rerank for Voyage and Bedrock), check status, last checked time, and price overrides.
- **Capability matrix.** A static registry lists, for each provider, the capabilities and the models available for each. Pickers read it through the API. It's maintained in code, alongside the price table.
- **Bedrock role assumption.** The platform has its own AWS identity (a task role in AWS; local credentials or none in `docker compose`). Each Organisation gets a stable, unguessable external ID generated by the platform. Assumed-role sessions are cached until shortly before they expire.
- **Credential verifier port.** One check operation per provider. Anthropic and OpenAI do a minimal model call or model list; Bedrock checks role assumption and then model access; Voyage does a one-token embed. It returns either success or a typed failure reason. The fake verifier returns whatever the test chooses.
- **Model gateway seam.** This slice introduces the single factory that turns a credential plus a model name into a Pydantic AI model (chat) or an embedder client (embeddings or rerank). Every later model call goes through it, and tests substitute the fakes there.
- **API.** Credential CRUD, check, rotate. Model list per credential and capability. Default Model get/set. Price table read and per-credential overrides. All mutations are Owner-only and go through the audit module. No response schema contains a secret field.
- **Dependency check on delete.** The credentials module exposes a "who references me" query. Later specs register their references to it: Project Embedding Model, Agent model override, reranker, guardrail classifier. Delete is blocked while any reference exists.
- **Price table.** Lives in the repo as data, keyed by provider and model, with effective-from dates. It's loaded into a table on migrate or seed. Overrides are stored per credential. Cost calculation lives here as one pure function: (credential, model, token counts, at-time) → cost. Spec 07 uses it.
- **Theme model.** One per Organisation:
  - colour tokens: primary, on-primary, surface, on-surface, accent, muted, each with a dark-mode value;
  - corner radius;
  - font family from an allowlist of Google Fonts;
  - logo and default avatar, uploaded to object storage through presigned uploads restricted by size and image type;
  - mode (light, dark or auto);
  - launcher type (bubble or inline) and position.
- **Theme resolution.** A pure function that resolves the Theme (and, from spec 06, the per-Agent override) into CSS custom properties. The Studio preview, the widget and the contrast checker all use it. Contrast is calculated with the WCAG relative-luminance formula, and it warns rather than blocks.
- **Studio UI.** Organisation settings tabs: Credentials (list, add wizard per provider, Bedrock trust-policy helper, check results), Models (Default Model, price table with overrides), Theme (form plus live preview rendering the shared UI primitives the widget will use).

## Testing Decisions

- **Good tests** assert what an Owner or Editor can observe through the API or UI, such as check results, masked suffixes, refusals and Audit Events. They never inspect ciphertext layout beyond "a secret is never returned".
- **Envelope encryption** is tested through its seal/open interface with the local key wrapper: round trip, tamper detection, and refusing a record sealed under a different key. The KMS adapter is covered with a stubbed AWS client (botocore Stubber) because it's a thin adapter.
- **API seam:**
  - credential lifecycle per provider and auth kind, with the fake verifier returning each failure reason;
  - rotate keeps the credential's identity;
  - delete blocked by references, using a test-registered reference;
  - an Editor can read but not write;
  - cross-tenant isolation, extending the parametrised suite from spec 01;
  - a response-schema test asserting that no credential endpoint ever returns secret material.
- **Bedrock role assumption** is tested through the verifier adapter with a stubbed STS client, covering the external ID being passed and session caching with the controllable clock.
- **Pure functions:** cost calculation (overrides take precedence; the right price is chosen for a given date), Theme resolution, and the contrast calculation against known WCAG reference pairs.
- **Frontend, network seam:** the add-credential wizard for each provider, including showing failure reasons; the Default Model picker filtered by capability; the price override form; the Theme editor updating the preview live; the contrast warning appearing and disappearing.
- **End-to-end:** an Owner adds a credential (the fake verifier in compose reports success), sets the Default Model, and changes the primary colour, and the preview updates.
- **Prior art:** fixtures from spec 01 (signed-in client per role, tenant factory, audit assertions).

## Out of Scope

- Per-Agent Theme overrides (spec 06), and using the Theme in the real widget (spec 06).
- Selecting an Embedding Model per Project (spec 03), and selecting a model per Agent (spec 04).
- Providers beyond Anthropic, OpenAI, Bedrock and Voyage.
- Automatic price updates from providers.
- Customer-managed KMS keys.

## Further Notes

- ADR-0006 governs the storage design. The cross-account role flow is the second-best interview story after the guardrails, so the Bedrock trust-policy helper deserves polish.
- The "who references me" registry keeps the credentials module from knowing about every consumer. Keep it that way.
