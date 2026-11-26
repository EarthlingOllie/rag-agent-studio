# 04: The rehearsal is a usable Studio

**Ticket:** `23-04` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** After `make rehearse` and a seed, a developer can open the Studio at the rehearsal's address, sign in, upload a Document and watch it become Ready.

**Blocked by:**
- `23-03`

**Status:** ready-for-agent

- [ ] The emulated distribution's address is the Studio URL and the uploads CORS origin in `local`
- [ ] Browser uploads work: presigned links point at an address the browser can reach
- [ ] Studio deep links load after a refresh, through a 404-to-index error response that only `local` adds
- [ ] Per-Visitor rate limits see the real client address: the emulator's network ranges are trusted proxies in `local`
- [ ] The seed runs as a one-off task through the unchanged seed script, and the demo Owner can sign in
- [ ] An uploaded Document becomes Ready, proving the worker reaches the queue, database, cache, bucket and key service by the addresses Terraform gave it
- [ ] A second `terraform plan` after an apply shows no changes, and the wrapper fails if it does
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
