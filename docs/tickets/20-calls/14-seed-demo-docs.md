# 14: Seed, demo and docs

**Ticket:** `20-14` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** The demo shows Calls when it can, and the docs say what Calls are and how to try them.

**Blocked by:**
- `20-05`
- `20-07`

**Status:** done

- [x] With `SEED_ELEVENLABS_API_KEY` and a public base URL set, `make seed` adds the ElevenLabs credential and turns calling on for the Product FAQ; without them calling stays off and the seed is unchanged
- [x] The seed stays idempotent, and `make seed-reset` removes the remote agent it made
- [x] `.env.example`, the README (highlights, quickstart extras) and docs/plan.md (scope, architecture) cover Calls; docs/demo.md gains a short Calls walkthrough
- [x] The AWS demo's deploy passes the public base URL to the API
- [x] The Demo Organisation's glossary entry says when it takes Calls
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
