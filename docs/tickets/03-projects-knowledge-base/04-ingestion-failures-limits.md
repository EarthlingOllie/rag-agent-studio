# 04: Ingestion failures and limits

**Ticket:** `03-04` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Unsupported or oversized files are refused before upload with a clear message. Failed Documents explain what went wrong and can be retried. Projects respect a Document quota.

**Blocked by:**
- [03-02: Upload a Document to Ready](02-upload-document-to-ready.md)

**Status:** in-progress

- [ ] File type and size are validated before upload, and unsupported types are refused with a message
- [ ] Failures are categorised (unsupported content, conversion, provider, quota) with readable messages
- [ ] Editors can retry a failed Document, and transient failures retry automatically with backoff
- [ ] The per-Project Document quota is enforced with a clear message
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
