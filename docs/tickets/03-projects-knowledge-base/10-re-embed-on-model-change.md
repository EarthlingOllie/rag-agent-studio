# 10: Re-embed on Embedding Model change

**Ticket:** `03-10` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Editors can switch a Project's Embedding Model at any time. A background job re-embeds the Knowledge Base with visible progress while the old vectors keep serving, then switches over in one step. A failure leaves the Project untouched.

**Blocked by:**
- [03-09: Provider Embedding Models](09-provider-embedding-models.md)

**Status:** done

- [x] Changing the model with Documents present sets the new model as pending and starts a re-embed job
- [x] Progress is visible; the old vectors serve until an atomic switch, after which they're deleted
- [x] A failed job leaves the active model unchanged, with the error shown
- [x] Documents uploaded during the job are embedded with both models
- [x] Model changes are recorded as Audit Events
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
