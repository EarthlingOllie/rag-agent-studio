# 03: Model gateway and Default Model

**Ticket:** `02-03` · **Spec:** [Provider Credentials and Theme](../../specs/02-provider-credentials-theme-spec.md)

**What to build:** Owners pick the Organisation's Default Model from a chat-capable credential's models. Behind this is the single model gateway that every later model call goes through, and where tests plug in their fakes.

**Blocked by:**
- [02-01: API-key Provider Credentials](01-api-key-credentials.md)

**Status:** in-progress

- [ ] One factory turns a credential and model name into a Pydantic AI chat model, an embedder or a reranker, with fakes injectable at that one point
- [ ] The model list for each credential is filtered by capability
- [ ] Owners set the Default Model from chat-capable credentials only
- [ ] The Default Model's credential is registered as a reference
- [ ] The Studio has a Models tab
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
