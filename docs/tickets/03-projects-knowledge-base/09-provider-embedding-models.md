# 09: Provider Embedding Models

**Ticket:** `03-09` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Editors choose a Project's Embedding Model: the platform's local model (the default) or a Voyage, OpenAI or Bedrock model through an embedding-capable Provider Credential. Until re-embedding exists (03-10), the model can only be changed while the Project has no Documents.

**Blocked by:**
- [03-02: Upload a Document to Ready](02-upload-document-to-ready.md)
- [02-03: Model gateway and Default Model](../02-provider-credentials-theme/03-model-gateway-default-model.md)

**Status:** in-progress

- [ ] An Embedding Model registry records provider, dimension and tokenizer for each model
- [ ] New Projects default to the local model, and a provider model can be chosen from embedding-capable credentials, registering a reference
- [ ] Changing the model is refused while the Project has Documents
- [ ] A retrieval probe endpoint returns the top-k Chunks by vector, for tests and diagnostics
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
