# 01: Seed foundation

**Ticket:** `10-01` · **Spec:** [Seed data and showcase](../../specs/10-seed-showcase-spec.md)

**What to build:** `make seed` creates the demo Organisation: Owner and Editor accounts, the Northwind Project with synthetic Documents and Tags, a Theme and a labelled demo model provider, so the demo needs no API keys. `make seed-reset` restores it.

**Blocked by:**
- [03-06: Tags](../03-projects-knowledge-base/06-tags.md)
- [02-05: Theme editor](../02-provider-credentials-theme/05-theme-editor.md)
- [04-07: Full AgentConfig editor](../04-agents-retrieval-playground/07-full-agentconfig-editor.md)

**Status:** done

- [x] The seed goes through application services, is idempotent, and `seed-reset` recreates only the demo Organisation
- [x] A demo provider adapter is clearly labelled as a demo model
- [x] Owner and Editor accounts are created and their sign-in details printed
- [x] The Northwind Project has synthetic Documents (one with an injection footnote) with a licence note, plus Tags and a Theme
- [x] A real credential can optionally be read from the environment
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
